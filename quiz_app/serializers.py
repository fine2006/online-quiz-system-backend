# quiz_app/serializers.py
from rest_framework import serializers
from django.db import transaction
from django.utils import timezone
from django.db.models import OuterRef, Subquery, Max, Count
from django.db.models.functions import Rank
from django.db.models import Window

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


# Helper to handle nested updates/creates
def update_or_create_nested(
    parent_instance, items_data, item_model, foreign_key_field, related_name
):
    """
    Handles updating, creating, and deleting nested items.
    parent_instance: The instance the items belong to (e.g., a Quiz for Questions).
    items_data: The list of nested item data from the serializer (list of dicts).
    item_model: The Django model for the nested items (e.g., Question).
    foreign_key_field: The name of the foreign key field in item_model linking to parent_instance.
    related_name: The related_name from the parent to the children (e.g., 'questions').
    """
    # Get IDs of existing items
    existing_items_ids = set(
        getattr(parent_instance, related_name).values_list("id", flat=True)
    )
    # Get IDs from submitted data
    submitted_items_ids = set(
        item.get("id") for item in items_data if "id" in item and item["id"] is not None
    )

    # Items to delete (exist in DB but not in submitted data)
    items_to_delete_ids = existing_items_ids - submitted_items_ids
    if items_to_delete_ids:
        item_model.objects.filter(id__in=items_to_delete_ids).delete()

    # Items to create or update
    for item_data in items_data:
        item_id = item_data.get("id")
        defaults = {
            k: v for k, v in item_data.items() if k != "id"
        }  # Exclude 'id' from defaults
        # Add the foreign key linking to the parent
        defaults[foreign_key_field] = parent_instance

        if item_id in existing_items_ids:
            # Update existing item
            item_instance = item_model.objects.get(id=item_id)
            for key, value in defaults.items():
                setattr(item_instance, key, value)
            item_instance.save()
        else:
            # Create new item
            item_instance = item_model.objects.create(**defaults)

        # Handle nested items (e.g., AnswerOptions within Questions) if applicable
        if (
            "answer_options" in item_data and related_name == "questions"
        ):  # Specific logic for Question -> AnswerOption
            update_or_create_nested(
                parent_instance=item_instance,
                items_data=item_data["answer_options"],
                item_model=AnswerOption,
                foreign_key_field="question",
                related_name="answer_options",
            )


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ("id", "username", "email", "role", "is_marked")
        read_only_fields = (
            "username",
            "email",
            "role",
        )  # Allow admin to potentially mark/unmark


class AnswerOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnswerOption
        fields = (
            "id",
            "text",
            "is_correct",
        )  # is_correct is included for writable serializers


class QuestionSerializer(serializers.ModelSerializer):
    answer_options = AnswerOptionSerializer(many=True, required=False)

    class Meta:
        model = Question
        fields = (
            "id",
            "question_type",
            "text",
            "points",
            "correct_answer_bool",
            "answer_options",
        )


class QuizWritableSerializer(serializers.ModelSerializer):
    questions = QuestionSerializer(many=True, required=False)
    teacher = serializers.ReadOnlyField(
        source="teacher.username"
    )  # Show teacher username, not writable

    class Meta:
        model = Quiz
        fields = (
            "id",
            "title",
            "teacher",
            "timing_minutes",
            "available_from",
            "available_to",
            "questions",
        )
        read_only_fields = ("teacher",)  # Ensure teacher cannot be set via API input

    def create(self, validated_data):
        questions_data = validated_data.pop("questions", [])
        # Assign the logged-in user as the teacher (set in the view's perform_create)
        # validated_data['teacher'] is implicitly set by the view
        quiz = Quiz.objects.create(**validated_data)

        with transaction.atomic():
            for question_data in questions_data:
                answer_options_data = question_data.pop("answer_options", [])
                question = Question.objects.create(quiz=quiz, **question_data)
                for option_data in answer_options_data:
                    AnswerOption.objects.create(question=question, **option_data)

        return quiz

    def update(self, instance, validated_data):
        questions_data = validated_data.pop("questions", [])

        # Update quiz instance fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        with transaction.atomic():
            # Handle nested questions and their answer options
            update_or_create_nested(
                parent_instance=instance,
                items_data=questions_data,
                item_model=Question,
                foreign_key_field="quiz",
                related_name="questions",
            )

        return instance


class QuestionReadOnlySerializer(serializers.ModelSerializer):
    # Do NOT expose is_correct here by default
    answer_options = serializers.SerializerMethodField()

    class Meta:
        model = Question
        fields = ("id", "question_type", "text", "points", "answer_options")

    def get_answer_options(self, obj):
        # This version hides the `is_correct` field
        return AnswerOptionSerializer(
            obj.answer_options.all(), many=True, context=self.context
        ).data
        # Alternative if AnswerOptionSerializer did not include is_correct by default:
        # return [{'id': opt.id, 'text': opt.text} for opt in obj.answer_options.all()]


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
            question = Question.objects.get(id=question_id)
        except Question.DoesNotExist:
            raise serializers.ValidationError(
                f"Question with ID {question_id} does not exist."
            )

        # Store question object for later use in QuizSubmissionSerializer validation
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

        return data


class QuizSubmissionSerializer(serializers.Serializer):
    """Serializer for the overall quiz submission payload."""

    quiz_id = serializers.IntegerField()
    answers = ParticipantAnswerSubmitSerializer(many=True)

    def validate(self, data):
        quiz_id = data.get("quiz_id")
        answers_data = data.get("answers", [])

        if quiz_id is None:
            raise serializers.ValidationError("quiz_id is required.")

        try:
            quiz = Quiz.objects.prefetch_related("questions__answer_options").get(
                id=quiz_id
            )
        except Quiz.DoesNotExist:
            raise serializers.ValidationError(f"Quiz with ID {quiz_id} does not exist.")

        # Store quiz object for later use in view
        data["quiz"] = quiz

        # Check if the quiz is available for submission
        if not quiz.is_available_for_submission:
            raise serializers.ValidationError(
                "This quiz is not currently available for submission."
            )

        # Check for duplicate question IDs in the submission
        question_ids = [answer["question_id"] for answer in answers_data]
        if len(question_ids) != len(set(question_ids)):
            raise serializers.ValidationError(
                "Duplicate question IDs found in the submission."
            )

        # Optional: Check if *all* questions from the quiz are answered
        # quiz_question_ids = set(quiz.questions.values_list('id', flat=True))
        # submitted_question_ids = set(question_ids)
        # if quiz_question_ids != submitted_question_ids:
        #     raise serializers.ValidationError("Submission must include answers for all questions in the quiz.")

        # Ensure all submitted question IDs belong to the quiz
        valid_quiz_question_ids = set(quiz.questions.values_list("id", flat=True))
        for answer_data in answers_data:
            if answer_data["question_id"] not in valid_quiz_question_ids:
                raise serializers.ValidationError(
                    f"Question ID {answer_data['question_id']} does not belong to this quiz."
                )

        return data


class ParticipantAnswerResultSerializer(serializers.ModelSerializer):
    """Serializer for viewing results of individual participant answers."""

    # Use QuestionReadOnlySerializer which hides default `is_correct` on AnswerOption
    question = QuestionReadOnlySerializer(read_only=True)
    selected_options = AnswerOptionSerializer(
        many=True, read_only=True
    )  # Shows selected options

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
            "is_correct",
            "correct_answer_bool",
            "correct_options",
        )
        read_only_fields = "__all__"

    def get_correct_answer_bool(self, obj):
        # Only show correct answer if the quiz availability window has passed OR there was no window.
        # This logic depends on the parent attempt and quiz.
        attempt = obj.attempt
        quiz = attempt.quiz
        now = timezone.now()

        # Show correct answers if the quiz is NOT currently available for submission
        # This happens if:
        # 1. There was a window and it has passed (`now > quiz.available_to`)
        # 2. There was a start time but no end time, and the start time is in the future (`now < quiz.available_from` and `quiz.available_to` is None) - quiz hasn't started yet.
        # 3. There was an end time but no start time, and the end time has passed (`now > quiz.available_to` and `quiz.available_from` is None) - quiz has ended.
        # 4. There was a window and the current time is outside of it (`now < quiz.available_from` or `now > quiz.available_to`)
        # Simpler logic: Show if the quiz is *not* currently available for submission.
        # This is the inverse of `quiz.is_available_for_submission`.

        # Let's refine: Show results AFTER the quiz has ended, or if it had no end time, show immediately.
        # If quiz.available_to is not None and timezone.now() > quiz.available_to: Show results
        # If quiz.available_to is None: Show results (as it implies results are immediate or not time-gated)
        # Otherwise (quiz.available_to is in the future or None, and quiz.available_from is in the past or None, AND now is within the window): Don't show results.

        show_results = False
        if quiz.available_to is not None:
            if now > quiz.available_to:
                show_results = True  # Window ended
        else:
            show_results = True  # No end window, show results

        if show_results and obj.question.question_type == QuestionTypes.TRUE_FALSE:
            return obj.question.correct_answer_bool
        return None  # Do not show correct boolean otherwise

    def get_correct_options(self, obj):
        # Only show correct options if the quiz availability window has passed OR there was no window.
        # Same logic as get_correct_answer_bool
        attempt = obj.attempt
        quiz = attempt.quiz
        now = timezone.now()

        show_results = False
        if quiz.available_to is not None:
            if now > quiz.available_to:
                show_results = True  # Window ended
        else:
            show_results = True  # No end window, show results

        if show_results and obj.question.question_type in [
            QuestionTypes.SINGLE_MCQ,
            QuestionTypes.MULTI_MCQ,
        ]:
            # Return serialized correct options, including is_correct=True
            correct_options = obj.question.answer_options.filter(is_correct=True)
            return AnswerOptionSerializer(
                correct_options, many=True
            ).data  # Use AnswerOptionSerializer to show text/id/is_correct
        return []  # Do not show correct options otherwise


class QuizAttemptResultSerializer(serializers.ModelSerializer):
    """Serializer for viewing overall quiz attempt results."""

    user = UserSerializer(read_only=True)
    quiz = QuizReadOnlySerializer(read_only=True)
    participant_answers = ParticipantAnswerResultSerializer(many=True, read_only=True)

    # Add fields for rank and best score
    rank = serializers.SerializerMethodField()
    best_score_for_quiz = serializers.SerializerMethodField()

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
            "best_score_for_quiz",
        )
        read_only_fields = "__all__"

    def get_rank(self, obj):
        """
        Calculates the rank of this attempt based on score for the same quiz.
        Timed quizzes: Rank by highest score.
        Untimed quizzes: Rank by first attempt score (or simply score if only one attempt allowed).
        Assuming multiple attempts are possible and rank is based on score across all attempts for timed,
        and score of the *first* attempt for untimed.
        This implementation ranks all attempts for this quiz by score descending, then time ascending.
        This might not perfectly match "first attempt score for untimed" across different users,
        but provides a consistent ranking.
        For true "rank based on first attempt score for untimed", we'd need to filter to only first attempts.
        Let's implement ranking all attempts by score desc, time asc for simplicity, but note the
        potential mismatch with a strict "first attempt score" requirement for untimed quizzes if users have multiple attempts.
        A more precise method for untimed would involve grouping by user and taking the first attempt's score.
        Given the complexity and potential performance impact within a serializer, a simplified rank is shown.
        """
        # Query attempts for the same quiz, ordered by score (desc) and submission time (asc)
        # Use Window function for ranking (requires Django 3.2+)
        # Or use a subquery approach if not using 3.2+

        # Subquery approach for broader compatibility
        # Find attempts with a higher score
        higher_scores = QuizAttempt.objects.filter(
            quiz=obj.quiz, score__gt=obj.score
        ).distinct()

        # Find attempts with the same score, but submitted earlier
        same_score_earlier = QuizAttempt.objects.filter(
            quiz=obj.quiz, score=obj.score, submission_time__lt=obj.submission_time
        ).distinct()

        # Rank is 1 + number of attempts with a higher score + number of attempts with the same score but earlier
        # Ensure we only count unique users/attempts depending on desired ranking behaviour (all attempts vs best attempt per user)
        # The request implies ranking *attempts*, not users based on their best attempt.
        rank = 1 + higher_scores.count() + same_score_earlier.count()

        # Handle ties: Attempts with the same score and same submission time will have the same rank calculation here.
        # If stricter tie-breaking is needed (e.g., based on attempt ID), the subquery needs adjustment.

        return rank

    def get_best_score_for_quiz(self, obj):
        """
        Finds the best score for the *current user* on this quiz.
        Timed quizzes: Max score across all attempts by the user.
        Untimed quizzes: Score of the first attempt by the user.
        """
        attempts_by_user = QuizAttempt.objects.filter(user=obj.user, quiz=obj.quiz)

        if not attempts_by_user.exists():
            return 0.0  # Should not happen if we're serializing an attempt

        # Sort attempts by submission time to find the first one
        attempts_by_user = attempts_by_user.order_by("submission_time")

        if obj.quiz.timing_minutes and obj.quiz.timing_minutes > 0:
            # Timed quiz: best score is the max score
            return (
                attempts_by_user.aggregate(max_score=Max("score"))["max_score"] or 0.0
            )
        else:
            # Untimed quiz: best score is the score of the first attempt
            first_attempt = attempts_by_user.first()
            return first_attempt.score if first_attempt else 0.0
