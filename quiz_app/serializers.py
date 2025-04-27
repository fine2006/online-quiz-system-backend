# quiz_app/serializers.py

from django.db import transaction
from django.utils import timezone

# Import the necessary serializers module
from rest_framework import serializers

# Import necessary models and Roles Enum, and QuestionTypes Enum
from .models import (
    CustomUser,
    Quiz,
    Question,
    AnswerOption,
    QuizAttempt,
    ParticipantAnswer,
    Roles,
    QuestionTypes,
)

# Imports needed for result serializers' calculations
from django.db.models import Max, Q  # Import Q for complex filtering
# Consider importing F and Q objects if complex queries are needed in serializers
# from django.db.models import F

# Imports needed for rank calculation (if using Window functions - requires Django 3.2+)
from django.db.models import Window
from django.db.models.functions import Rank  # Note: Rank is a Window function


# Helper to get QuestionTypes Enum member from string value
# Create a dictionary mapping the string value of each Enum member to the member itself
QUESTION_TYPE_ENUM_MAP = {member.value: member for member in QuestionTypes}


def get_question_type_enum_from_string(value_string):
    """Looks up a QuestionTypes Enum member based on its string value."""
    return QUESTION_TYPE_ENUM_MAP.get(value_string)


# --- Basic Serializers ---


class UserSerializer(serializers.ModelSerializer):
    """
    Serializer for the CustomUser model.
    Used by dj-rest-auth for the /api/auth/user/ endpoint and in read-only contexts.
    """

    class Meta:
        model = CustomUser
        fields = ["id", "username", "email", "role", "is_marked"]
        # Fields are typically read-only when this serializer is used in other read-only serializers
        # For the /api/auth/user/ endpoint for updating, a different serializer might be configured
        # via dj-rest-auth settings (e.g., USER_DETAILS_SERIALIZER) that makes these fields writable.
        # For this file's context (read-only in other serializers), read_only_fields can be set or omitted.
        # Let's explicitly mark key fields as read-only as per common usage in other serializers.
        read_only_fields = [
            "id",
            "username",
            "email",
            "role",
        ]  # is_marked might be editable by admin user details endpoint


# --- Read-Only Nested Serializers ---


# This is the read-only serializer for AnswerOption used in QuestionReadOnlySerializer and ParticipantAnswerResultSerializer
# It should NOT expose the 'is_correct' field by default.
class AnswerOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnswerOption
        # FIX: Remove 'is_correct' from the fields list for the general read-only serializer
        fields = (
            "id",
            "text",
            # "is_correct", # Removed
        )
        # Setting all fields listed above as read-only
        read_only_fields = fields


# This is the read-only serializer for Question used in QuizReadOnlySerializer and ParticipantAnswerResultSerializer
# Depends on AnswerOptionSerializer
class QuestionReadOnlySerializer(serializers.ModelSerializer):
    # Use AnswerOptionSerializer here which now correctly hides is_correct
    answer_options = AnswerOptionSerializer(many=True, read_only=True)

    class Meta:
        model = Question
        fields = ("id", "question_type", "text", "points", "answer_options")
        # FIX: read_only_fields must be a list or tuple
        read_only_fields = fields


# --- Writable Nested Serializers ---


# This is the writable serializer for AnswerOption used in QuizQuestionWritableSerializer
# This serializer *does* need the 'is_correct' field for teachers to set.
# No dependencies on other serializers defined in this file.
class QuizAnswerOptionWritableSerializer(serializers.ModelSerializer):
    """
    Writable serializer for AnswerOption. Handles saving individual option instances.
    Parent serializer is responsible for passing the 'question' instance during save.
    """

    class Meta:
        model = AnswerOption
        fields = ["id", "text", "is_correct"]  # Include is_correct here for writing
        extra_kwargs = {
            "id": {
                "read_only": False,
                "required": False,
            }  # Allow ID to be sent for updates
        }

    def validate(self, data):
        # Simple validation: ensure text is not empty
        if not data.get("text"):
            raise serializers.ValidationError("Answer option text cannot be empty.")
        # No need to validate 'question' FK here; it's set by the parent serializer/save method.
        return data


# This is the writable serializer for Question used in QuizWritableSerializer
# Depends on QuizAnswerOptionWritableSerializer
class QuizQuestionWritableSerializer(serializers.ModelSerializer):
    """
    Writable serializer for Question, includes nested AnswerOptions.
    Overrides create/update to handle nested answer options and set the 'quiz' FK.
    This is where the answer_options.set() logic for updates lives.
    """

    # Define nested options using the writable serializer
    answer_options = QuizAnswerOptionWritableSerializer(many=True, required=False)
    correct_answer_bool = serializers.BooleanField(required=False, allow_null=True)

    class Meta:
        model = Question
        fields = [
            "id",
            "quiz",
            "question_type",
            "text",
            "points",
            "answer_options",
            "correct_answer_bool",
        ]
        extra_kwargs = {
            "id": {"read_only": False, "required": False},  # Allow ID for updates
            "quiz": {
                "read_only": True
            },  # Quiz FK is set by parent Quiz serializer's save method
        }

    # --- Refactored Validation ---
    # Consolidate all validation logic here in the main validate method
    def validate(self, data):
        # Get all necessary fields from the 'data' dictionary passed to validate
        question_type = data.get("question_type")
        answer_options = data.get(
            "answer_options"
        )  # This is the validated list of option data
        correct_answer_bool = data.get("correct_answer_bool")  # Check if it's in data

        # Convert string question_type to Enum using the helper
        # Use the helper function defined at the top
        question_type_enum = get_question_type_enum_from_string(question_type)

        # --- Check field requirements based on create/update (self.instance) and data presence ---

        # Require question_type on create
        if question_type is None and self.instance is None:
            raise serializers.ValidationError(
                {"question_type": "This field is required."}
            )

        # If question_type is provided, validate its relation to other fields
        if question_type_enum:  # Check if a valid enum member was found
            if question_type_enum in [
                QuestionTypes.SINGLE_MCQ,
                QuestionTypes.MULTI_MCQ,
            ]:
                # Check for correct_answer_bool presence when it shouldn't exist
                if correct_answer_bool is not None:
                    raise serializers.ValidationError(
                        {
                            "correct_answer_bool": f"{question_type} questions should not have correct_answer_bool."
                        }
                    )
                # Require answer_options on create or if explicitly provided in update data
                # If it's create OR (it's update AND 'answer_options' key is present in data)
                if answer_options is None and (
                    self.instance is None or "answer_options" in data
                ):
                    raise serializers.ValidationError(
                        {
                            "answer_options": f"{question_type} questions must have answer options."
                        }
                    )

                # Validate content of answer options list (counts, correct answers)
                if (
                    answer_options is not None
                ):  # Only check if answer_options data was provided
                    if not answer_options:
                        raise serializers.ValidationError(
                            {
                                "answer_options": "MCQ questions must have answer options."
                            }
                        )

                    correct_count = sum(
                        opt.get("is_correct", False) for opt in answer_options
                    )

                    if (
                        question_type_enum == QuestionTypes.SINGLE_MCQ
                        and correct_count != 1
                    ):
                        raise serializers.ValidationError(
                            "Single MCQ must have exactly one correct answer."
                        )

                    if (
                        question_type_enum == QuestionTypes.MULTI_MCQ
                        and correct_count < 1
                    ):
                        raise serializers.ValidationError(
                            "Multi MCQ must have at least one correct answer."
                        )

            elif question_type_enum == QuestionTypes.TRUE_FALSE:
                # Check for answer_options presence when it shouldn't exist
                if answer_options is not None:
                    raise serializers.ValidationError(
                        {
                            "answer_options": f"{question_type} questions should not have answer options."
                        }
                    )
                # Require correct_answer_bool on create or if present in update data
                # If it's create OR (it's update AND 'correct_answer_bool' key is present in data)
                if correct_answer_bool is None and (
                    self.instance is None or "correct_answer_bool" in data
                ):
                    raise serializers.ValidationError(
                        {
                            "correct_answer_bool": f"{question_type} questions must specify correct_answer_bool (true/false)."
                        }
                    )
            # If question_type is provided but not recognized, this case is handled by DRF default validation
            # If question_type is provided but doesn't map to a known enum value, get_question_type_enum_from_string returns None,
            # and the outer `if question_type_enum:` block is skipped. This is handled implicitly by default validation on the field itself.

        # Check text requirement
        # If it's create OR (it's update AND 'text' key is present in data)
        if not data.get("text") and (self.instance is None or "text" in data):
            raise serializers.ValidationError(
                {"text": "Question text cannot be empty."}
            )

        # Check points requirement
        # If it's create OR (it's update AND 'points' key is present in data)
        points = data.get("points")
        if points is None and (self.instance is None or "points" in data):
            raise serializers.ValidationError({"points": "Points must be provided."})
        elif points is not None and (
            not isinstance(points, (int, float)) or points <= 0
        ):
            raise serializers.ValidationError(
                {"points": "Points must be a positive number."}
            )

        return data

    @transaction.atomic  # Ensure atomicity for question and its options
    def create(self, validated_data):
        # Override create to handle nested answer options and set the 'quiz' FK
        # 'quiz' instance is expected in validated_data because parent serializer passes it via save()
        answer_options_data = validated_data.pop(
            "answer_options", []
        )  # Pop nested data

        # Create the Question instance
        # validated_data should now contain 'quiz' instance passed by parent
        question_instance = Question.objects.create(
            **validated_data
        )  # 'quiz' FK is set here

        # Manually create answer options for the new question
        # No need to call .set() during initial creation, saving the option with the FK is sufficient.
        for option_data in answer_options_data:
            # AnswerOption serializer handles its own validation
            option_serializer = QuizAnswerOptionWritableSerializer(data=option_data)
            option_serializer.is_valid(raise_exception=True)
            # Create the AnswerOption instance, setting the 'question' FK
            option_serializer.save(
                question=question_instance
            )  # Pass question to set FK

        # Returning the instance after saving.
        return question_instance

    @transaction.atomic  # Ensure atomicity
    def update(self, instance, validated_data):
        # Override update to handle nested answer options (update, create, delete)
        # 'quiz' instance might be in validated_data if parent serializer passes it (good practice)
        answer_options_data = validated_data.pop("answer_options", None)

        # Update the Question instance fields (excluding nested data)
        # Iterate only over fields present in validated_data for PATCH
        for attr, value in validated_data.items():
            # Only set attributes that are not the nested 'answer_options' field itself
            if attr != "answer_options":
                setattr(instance, attr, value)
        instance.save()  # Save the main instance fields

        # --- Handle Nested Answer Options for THIS question instance ---
        # This happens *after* the question instance is saved/updated
        if (
            answer_options_data is not None
        ):  # Process options only if data is provided in request
            existing_options = {str(o.pk): o for o in instance.answer_options.all()}
            incoming_options_map = {
                str(o.get("id")): o for o in answer_options_data if o.get("id")
            }

            # Determine which existing options are NOT in the incoming data (to delete)
            options_to_delete = [
                option
                for pk, option in existing_options.items()
                if pk not in incoming_options_map
            ]

            # Delete options not in incoming data for THIS question
            if options_to_delete:
                # Use a list() to evaluate the queryset before deleting to avoid issues
                instance.answer_options.filter(
                    id__in=[opt.id for opt in options_to_delete]
                ).delete()

            processed_option_instances = []  # Collect updated/created question instances

            # Process incoming answer options for THIS question
            for option_data in answer_options_data:
                option_id = option_data.get("id")
                existing_option = (
                    existing_options.get(str(option_id)) if option_id else None
                )

                # Use the nested AnswerOption serializer to update or create the option instance
                option_serializer = QuizAnswerOptionWritableSerializer(
                    instance=existing_option,  # Pass existing instance for update or None for create
                    data=option_data,  # Data for the option
                    partial=True,  # Allow partial updates
                    # context={'request': self.context.get('request')}
                )
                option_serializer.is_valid(raise_exception=True)
                # Call the nested serializer's save method, explicitly setting the 'question' FK to THIS question instance
                processed_option_instance = option_serializer.save(
                    question=instance
                )  # Pass question instance

                processed_option_instances.append(processed_option_instance)

            # --- FIX: Use .set() to update answer_options for THIS question ---
            # After processing all options for this question, use .set() to update the relationship.
            # This replaces the question's answer_options with the updated/created set.
            # This was the crucial line the error message indicated was needed during update.
            instance.answer_options.set(processed_option_instances)
            # No need to save instance (Question) after .set() for ManyToOne/OneToMany.

        return instance


# --- Top-Level Read-Only Serializers ---


# This is the read-only serializer for Quiz
# Depends on UserSerializer and QuestionReadOnlySerializer
class QuizReadOnlySerializer(serializers.ModelSerializer):
    teacher = UserSerializer(read_only=True)  # Use read-only user serializer
    questions = QuestionReadOnlySerializer(many=True)
    is_available_for_submission = serializers.BooleanField(
        read_only=True
    )  # Expose model property
    has_availability_window = serializers.BooleanField(
        read_only=True
    )  # Expose model property

    class Meta:
        model = Quiz
        fields = (
            "id",
            "title",
            "teacher",
            "timing_minutes",
            "available_from",
            "available_to",
            "is_available_for_submission",
            "has_availability_window",
            "questions",
        )
        # FIX: read_only_fields must be a list or tuple, not the string "__all__"
        # To make all listed fields read-only, assign the fields tuple itself.
        read_only_fields = fields


# --- Submission Serializers ---


# No dependencies on other serializers defined in this file
class ParticipantAnswerSubmitSerializer(serializers.Serializer):
    """Serializer for submitting individual answers within a quiz attempt."""

    question_id = serializers.IntegerField()
    selected_option_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_empty=True,
        help_text="List of IDs for selected AnswerOption(s) (for MCQ types).",
    )
    selected_answer_bool = serializers.BooleanField(
        required=False,
        allow_null=True,
        help_text="Boolean answer for True/False questions (True or False).",
    )

    def validate(self, data):
        question_id = data.get("question_id")
        selected_option_ids = data.get("selected_option_ids", [])
        selected_answer_bool = data.get("selected_answer_bool")

        if question_id is None:
            raise serializers.ValidationError(
                "question_id is required for each answer."
            )

        try:
            # Use select_related for quiz to avoid N+1 queries later if accessing quiz properties
            question = (
                Question.objects.select_related("quiz")
                .prefetch_related("answer_options")
                .get(id=question_id)
            )
        except Question.DoesNotExist:
            raise serializers.ValidationError(
                f"Question with ID {question_id} does not exist."
            )

        # Store question object for later use in QuizSubmissionSerializer validation or view
        data["question"] = question

        # Validate based on question type
        if question.question_type == QuestionTypes.SINGLE_MCQ:
            if selected_answer_bool is not None:
                raise serializers.ValidationError(
                    "selected_answer_bool is not allowed for SINGLE_MCQ."
                )
            if len(selected_option_ids) > 1:
                raise serializers.ValidationError(
                    "Only one selected_option_id is allowed for SINGLE_MCQ."
                )
            # Validate selected option IDs belong to the question
            if selected_option_ids:
                valid_option_ids = set(
                    question.answer_options.values_list("id", flat=True)
                )
                if not set(selected_option_ids).issubset(valid_option_ids):
                    raise serializers.ValidationError(
                        "One or more selected_option_ids do not belong to this question."
                    )

        elif question.question_type == QuestionTypes.MULTI_MCQ:
            if selected_answer_bool is not None:
                raise serializers.ValidationError(
                    "selected_answer_bool is not allowed for MULTI_MCQ."
                )
            # Validate selected option IDs belong to the question
            if selected_option_ids:
                valid_option_ids = set(
                    question.answer_options.values_list("id", flat=True)
                )
                if not set(selected_option_ids).issubset(valid_option_ids):
                    raise serializers.ValidationError(
                        "One or more selected_option_ids do not belong to this question."
                    )

        elif question.question_type == QuestionTypes.TRUE_FALSE:
            if selected_option_ids:
                raise serializers.ValidationError(
                    "selected_option_ids are not allowed for TRUE_FALSE."
                )
            if selected_answer_bool is None:
                raise serializers.ValidationError(
                    "selected_answer_bool is required for TRUE_FALSE."
                )
        else:
            # Handle cases for potential other question types if needed
            if selected_option_ids or selected_answer_bool is not None:
                raise serializers.ValidationError(
                    f"Answer format invalid for question type {question.question_type}."
                )

        return data


# Depends on ParticipantAnswerSubmitSerializer
class QuizSubmissionSerializer(serializers.Serializer):
    """Serializer for the overall quiz submission payload."""

    quiz_id = serializers.IntegerField()
    # Use the submit serializer for nested answers
    answers = ParticipantAnswerSubmitSerializer(many=True)

    def validate(self, data):
        quiz_id = data.get("quiz_id")
        answers_data = data.get("answers", [])

        if quiz_id is None:
            raise serializers.ValidationError("quiz_id is required.")

        try:
            # Use prefetch_related for questions and answer_options for efficient access
            quiz = Quiz.objects.prefetch_related("questions__answer_options").get(
                id=quiz_id
            )
        except Quiz.DoesNotExist:
            raise serializers.ValidationError(f"Quiz with ID {quiz_id} does not exist.")

        # Store quiz object in validated_data for later use in view
        data["quiz"] = quiz

        # Check if the quiz is available for submission
        if not quiz.is_available_for_submission:
            raise serializers.ValidationError(
                "This quiz is not currently available for submission."
            )

        # Check for duplicate question IDs in the submission
        question_ids = [
            answer.get("question_id")
            for answer in answers_data
            if answer.get("question_id") is not None
        ]
        if len(question_ids) != len(set(question_ids)):
            raise serializers.ValidationError(
                "Duplicate question IDs found in the submission."
            )

        # Ensure all submitted question IDs belong to the quiz
        valid_quiz_question_ids = set(quiz.questions.values_list("id", flat=True))
        for answer_data in answers_data:
            # The validate method of ParticipantAnswerSubmitSerializer already
            # validated that the question exists and belongs to the quiz implicitly
            # if the question object was attached. Let's re-check explicitly here for safety.
            submitted_question_id = answer_data.get("question_id")
            if (
                submitted_question_id is not None
                and submitted_question_id not in valid_quiz_question_ids
            ):
                raise serializers.ValidationError(
                    f"Question ID {submitted_question_id} does not belong to this quiz."
                )

        # Optional: Check if *all* questions from the quiz are answered
        # This depends on whether incomplete submissions are allowed.
        # If all questions must be answered:
        # quiz_question_ids = set(quiz.questions.values_list('id', flat=True))
        # submitted_question_ids = set(question_ids)
        # if quiz_question_ids != submitted_question_ids:
        #      missing_ids = list(quiz_question_ids - submitted_question_ids)
        #      raise serializers.ValidationError(f"Submission must include answers for all questions. Missing IDs: {missing_ids}")

        return data


# Depends on QuestionReadOnlySerializer
class ParticipantAnswerResultSerializer(serializers.ModelSerializer):
    """Serializer for viewing results of individual participant answers."""

    # Use QuestionReadOnlySerializer which hides default `is_correct` on AnswerOption
    question = QuestionReadOnlySerializer(read_only=True)
    # Use the standard AnswerOptionSerializer to show selected options
    # which includes the `is_correct` field. Conditional visibility
    # is handled by parent serializer methods.
    selected_options = AnswerOptionSerializer(many=True, read_only=True)

    # Fields to conditionally show correct answers
    correct_answer_bool = serializers.SerializerMethodField()
    correct_options = serializers.SerializerMethodField()

    class Meta:
        model = ParticipantAnswer
        fields = (
            "id",
            "question",
            "selected_options",
            "selected_answer_bool",
            "is_correct",  # This is the calculated correctness of the participant's answer
            "correct_answer_bool",  # This is the serializer method field for the correct T/F answer
            "correct_options",  # This is the serializer method field for the correct MCQ options
        )
        # FIX: read_only_fields must be a list or tuple
        read_only_fields = fields

    # --- The expected method fields are defined here ---
    def get_correct_answer_bool(self, obj):  # <-- This method should exist
        # Only show correct answer if the quiz availability window has passed OR there was no end window.
        attempt = obj.attempt
        quiz = attempt.quiz
        now = timezone.now()

        # Show results if the quiz is NOT currently available for submission because the end time has passed
        show_results = False
        if quiz.available_to is not None and now > quiz.available_to:
            show_results = True

        # Also show results if there was no end time specified (results are immediate)
        if quiz.available_to is None:
            show_results = True

        if show_results and obj.question.question_type == QuestionTypes.TRUE_FALSE:
            # obj.question should be prefetched by QuizAttemptResultSerializer
            return obj.question.correct_answer_bool
        return None  # Do not show correct boolean otherwise

    def get_correct_options(self, obj):  # <-- This method should exist
        # Only show correct options if the quiz availability window has passed OR there was no end window.
        # Same logic as get_correct_answer_bool
        attempt = obj.attempt
        quiz = attempt.quiz
        now = timezone.now()

        show_results = False
        if quiz.available_to is not None and now > quiz.available_to:
            show_results = True
        if quiz.available_to is None:
            show_results = True

        if show_results and obj.question.question_type in [
            QuestionTypes.SINGLE_MCQ,
            QuestionTypes.MULTI_MCQ,
        ]:
            # obj.question should be prefetched by QuizAttemptResultSerializer
            # Return serialized correct options, including is_correct=True
            # Use AnswerOptionSerializer which excludes is_correct
            correct_options = obj.question.answer_options.filter(is_correct=True)
            return AnswerOptionSerializer(correct_options, many=True).data
        return []  # Do not show correct options otherwise


# Depends on UserSerializer, QuizReadOnlySerializer, ParticipantAnswerResultSerializer
class QuizAttemptResultSerializer(serializers.ModelSerializer):
    """Serializer for viewing overall quiz attempt results."""

    user = UserSerializer(read_only=True)
    # Use QuizReadOnlySerializer which includes QuestionReadOnlySerializer
    quiz = QuizReadOnlySerializer(read_only=True)
    # Use ParticipantAnswerResultSerializer for nested answer results
    participant_answers = ParticipantAnswerResultSerializer(many=True, read_only=True)

    # Add fields for rank and best score
    # Note: Rank calculation here within the serializer method can be inefficient for large datasets.
    # It's often better to annotate the rank in the view's queryset if possible.
    rank = serializers.SerializerMethodField()
    best_score_for_user_on_quiz = (
        serializers.SerializerMethodField()
    )  # Renamed for clarity

    class Meta:
        model = QuizAttempt
        fields = (
            "id",
            "user",
            "quiz",
            "score",
            "submission_time",
            "participant_answers",
            "rank",
            "best_score_for_user_on_quiz",  # Renamed field
        )
        # FIX: read_only_fields must be a list or tuple
        read_only_fields = fields

    def get_rank(self, obj):
        """
        Calculates the rank of this attempt based on score and submission time
        compared to other attempts for the same quiz.
        Orders by score (desc) then submission_time (asc).
        Note: This calculates the rank of the *attempt*, not the user's best rank.
        Consider performance for many attempts. This implementation calculates rank on the fly.
        """
        # Requires Django 3.2+ for Window functions
        # from django.db.models import Window
        # from django.db.models.functions import Rank

        # Find attempts with higher score OR same score and earlier time for the same quiz
        rank_query = (
            QuizAttempt.objects.filter(
                quiz=obj.quiz  # Filter for the same quiz as the current object
            )
            .filter(
                # Score is higher OR (Score is same AND submission is earlier)
                Q(score__gt=obj.score)
                | Q(score=obj.score, submission_time__lt=obj.submission_time)
            )
            .count()
        )

        # Rank is 1 + count of attempts that are definitively ranked above this one
        rank = rank_query + 1

        # Note: This basic count rank handles ties by giving the same rank number.
        # If multiple attempts have the exact same score and same submission time, they will have the same rank number.
        # The view's queryset annotation is the preferred way for performance.
        # If calculating here for simplicity but potential inefficiency:
        # For production or large datasets, calculate this in the view's queryset using Window functions
        # and access the annotated field in the serializer.

        return rank

    def get_best_score_for_user_on_quiz(self, obj):
        """
        Finds the best score for the *current user* on this quiz.
        Timed quizzes: Max score across all attempts by the user.
        Untimed quizzes: Score of the first attempt by the user.
        """
        attempts_by_user = QuizAttempt.objects.filter(user=obj.user, quiz=obj.quiz)

        if not attempts_by_user.exists():
            return 0.0  # Should not happen if we're serializing an attempt

        # Sort attempts by submission time to find the first one if needed
        attempts_by_user = attempts_by_user.order_by("submission_time")

        if obj.quiz.timing_minutes is not None and obj.quiz.timing_minutes > 0:
            # Timed quiz: best score is the max score
            return (
                attempts_by_user.aggregate(max_score=Max("score"))["max_score"] or 0.0
            )
        else:
            # Untimed quiz: best score is the score of the first attempt
            first_attempt = attempts_by_user.first()
            return first_attempt.score if first_attempt else 0.0


# --- Top-Level Writable Serializers ---


# This is the main writable serializer for Quiz
# Depends on QuizQuestionWritableSerializer
class QuizWritableSerializer(serializers.ModelSerializer):
    """
    Writable serializer for Quiz, with manual nested create/update orchestrated
    by overriding create/update methods and calling nested serializers' saves.
    """

    # Use the writable nested serializer for questions
    # This serializer's create/update will iterate through questions data and call
    # QuizQuestionWritableSerializer's create/update methods.
    questions = QuizQuestionWritableSerializer(many=True)

    # Read-only fields that will be returned in the response but not taken from input
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)

    class Meta:
        model = Quiz
        fields = [
            "id",
            "title",
            "timing_minutes",
            "available_from",
            "available_to",
            "questions",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    # No need for _update_or_create_nested helper with this approach,
    # as the logic is manually handled in create/update via nested serializers' saves.

    @transaction.atomic  # Ensure atomicity for the whole operation (Quiz, Questions, Options)
    def create(self, validated_data):
        # Extract nested questions data first
        questions_data = validated_data.pop(
            "questions"
        )  # Questions data is required for create

        # Create the main Quiz instance
        # The current user (teacher/admin) is automatically set as the creator by the view.
        quiz_instance = Quiz.objects.create(**validated_data)

        # Manually handle nested question creation using the nested serializer's create method
        # The nested serializer's create method handles its own children (options).
        for question_data in questions_data:
            # Create a new instance of the nested serializer for each question data dictionary
            question_serializer = QuizQuestionWritableSerializer(data=question_data)
            question_serializer.is_valid(raise_exception=True)
            # Call the nested serializer's save method, passing the parent quiz instance.
            # The nested serializer's create method handles saving itself,
            # setting the quiz FK, and handling its nested options.
            question_serializer.save(quiz=quiz_instance)  # Pass quiz instance to set FK

        return quiz_instance

    @transaction.atomic  # Ensure atomicity
    def update(self, instance, validated_data):
        # Extract nested questions data (might be absent in PATCH)
        questions_data = validated_data.get("questions", None)

        # Update main Quiz instance fields (excluding nested data)
        # Use a copy of validated_data keys to iterate safely while modifying
        # Only update fields present in validated_data for PATCH
        fields_to_update_on_quiz = {
            attr: value for attr, value in validated_data.items() if attr != "questions"
        }

        for attr, value in fields_to_update_on_quiz.items():
            setattr(instance, attr, value)
        instance.save()  # Save the main instance fields

        # Manually handle question updates/creations/deletions
        if (
            questions_data is not None
        ):  # Process options only if data is provided in request
            existing_questions = {str(o.pk): o for o in instance.questions.all()}
            incoming_questions_map = {
                str(o.get("id")): o for o in questions_data if q.get("id")
            }

            # Determine which existing options are NOT in the incoming data (to delete)
            options_to_delete = [
                option
                for pk, option in existing_options.items()
                if pk not in incoming_options_map
            ]

            # Delete options not in incoming data for THIS question
            if options_to_delete:
                # Use a list() to evaluate the queryset before deleting to avoid issues
                instance.questions.filter(
                    id__in=[q.id for q in options_to_delete]
                ).delete()

            processed_question_instances = []  # Collect updated/created question instances

            # Process incoming questions (update or create)
            for question_data in questions_data:
                question_id = question_data.get("id")
                existing_question = (
                    existing_questions.get(str(question_id)) if question_id else None
                )

                # Use the nested Question serializer's update/create method
                # Its update method handles nested options and the answer_options.set() call
                question_serializer = QuizQuestionWritableSerializer(
                    instance=existing_question,  # Pass existing instance for update or None for create
                    data=question_data,  # Data for the question and its options
                    partial=True,  # Allow partial updates
                    # context={'request': self.context.get('request')}
                )
                question_serializer.is_valid(raise_exception=True)
                # Call the nested serializer's save method, passing the parent quiz instance.
                # The nested serializer's save() method handles saving itself,
                # setting the quiz FK, and handling its nested options (including the .set()).
                processed_question_instance = question_serializer.save(
                    quiz=instance
                )  # Pass quiz instance

                processed_question_instances.append(processed_question_instance)

            # For ManyToOne/OneToMany relationship (Quiz <- Question),
            # saving the child with the parent FK is sufficient to link it.
            # Deletion of questions not in incoming data handles removal.
            # A final .set() on quiz.questions is typically not strictly necessary here
            # unless you have complex ManyToMany relationships managed on the parent side.
            # We rely on question_serializer.save(quiz=instance) to establish the link.

        # Re-save the main instance after nested updates if any fields were updated before
        # instance.save() # Usually not needed if fields were set directly and saved earlier

        return instance
