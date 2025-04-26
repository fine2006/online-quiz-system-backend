# quiz_app/models.py
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.core.validators import MinValueValidator
from django.db.models import Max, OuterRef, Subquery
from django.db.models.constraints import UniqueConstraint


class Roles(models.TextChoices):
    ADMIN = "ADMIN", _("Admin")
    TEACHER = "TEACHER", _("Teacher")
    STUDENT = "STUDENT", _("Student")


class QuestionTypes(models.TextChoices):
    SINGLE_MCQ = "SINGLE_MCQ", _("Single Correct Answer MCQ")
    MULTI_MCQ = "MULTI_MCQ", _("Multiple Correct Answers MCQ")
    TRUE_FALSE = "TRUE_FALSE", _("True/False")


class CustomUser(AbstractUser):
    role = models.CharField(max_length=50, choices=Roles.choices, default=Roles.STUDENT)
    is_marked = models.BooleanField(default=False)  # To indicate a banned student

    # Add related_name to avoid clashes
    groups = models.ManyToManyField(
        "auth.Group",
        verbose_name=_("groups"),
        blank=True,
        help_text=_(
            "The groups this user belongs to. A user will get all permissions "
            "granted to each of their groups."
        ),
        related_name="user_groups",  # Custom related_name
        related_query_name="user_group",
    )
    user_permissions = models.ManyToManyField(
        "auth.Permission",
        verbose_name=_("user permissions"),
        blank=True,
        help_text=_("Specific permissions for this user."),
        related_name="user_permissions",  # Custom related_name
        related_query_name="user_permission",
    )

    def is_admin(self):
        return self.role == Roles.ADMIN

    def is_teacher(self):
        return self.role == Roles.TEACHER

    def is_student(self):
        return self.role == Roles.STUDENT

    def __str__(self):
        return self.username


class Quiz(models.Model):
    title = models.CharField(max_length=255)
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="quizzes"
    )
    timing_minutes = models.PositiveIntegerField(
        validators=[MinValueValidator(1)]
    )  # Duration per attempt
    available_from = models.DateTimeField(null=True, blank=True)
    available_to = models.DateTimeField(null=True, blank=True)

    @property
    def has_availability_window(self):
        return self.available_from is not None and self.available_to is not None

    @property
    def is_available_for_submission(self):
        now = timezone.now()
        if self.has_availability_window:
            # Check if current time is within the window
            return self.available_from <= now <= self.available_to
        else:
            # No window means always available until manually closed/removed,
            # or perhaps better, always available for submission *unless* the window has passed.
            # Let's interpret 'no window' as 'always open for submission'.
            # If we want 'always open until manually closed', we need another flag.
            # Sticking to the prompt: no window means available, window means check time.
            # Alternative interpretation: 'available_to' being null means it's available forever from 'available_from'.
            # Let's use the prompt's interpretation: `has_availability_window` checks if *both* are set. If not both, it's considered "no window", meaning it's available.
            # Refined logic: Available if NO window set OR current time is within the window.
            if self.available_from is None and self.available_to is None:
                return True  # No window, always available
            elif self.available_from is not None and self.available_to is not None:
                return self.available_from <= now <= self.available_to
            elif self.available_from is not None and self.available_to is None:
                return (
                    self.available_from <= now
                )  # Available from a certain time, no end
            elif self.available_from is None and self.available_to is not None:
                return (
                    now <= self.available_to
                )  # Available until a certain time, no start

    def __str__(self):
        return self.title


class Question(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="questions")
    question_type = models.CharField(max_length=50, choices=QuestionTypes.choices)
    text = models.TextField()
    points = models.FloatField(default=1.0, validators=[MinValueValidator(0.0)])
    correct_answer_bool = models.BooleanField(
        null=True, blank=True
    )  # For True/False questions

    def __str__(self):
        return f"Q: {self.text[:50]}... ({self.quiz.title})"


class AnswerOption(models.Model):
    question = models.ForeignKey(
        Question, on_delete=models.CASCADE, related_name="answer_options"
    )
    text = models.CharField(max_length=255)
    is_correct = models.BooleanField()

    def __str__(self):
        return f"Option: {self.text[:50]}... (Correct: {self.is_correct})"


class QuizAttempt(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="quiz_attempts"
    )
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="attempts")
    score = models.FloatField(default=0.0)  # Calculated upon submission
    submission_time = models.DateTimeField(auto_now_add=True)

    def calculate_score(self):
        """
        Calculates the total score for the attempt based on the correctness
        of participant answers. Assumes participant_answer.is_correct is already set.
        """
        total_score = 0.0
        for participant_answer in self.participant_answers.filter(is_correct=True):
            total_score += participant_answer.question.points
        self.score = total_score
        self.save()

    def __str__(self):
        return (
            f"{self.user.username}'s attempt on {self.quiz.title} ({self.score} points)"
        )


class ParticipantAnswer(models.Model):
    attempt = models.ForeignKey(
        QuizAttempt, on_delete=models.CASCADE, related_name="participant_answers"
    )
    question = models.ForeignKey(
        Question, on_delete=models.CASCADE, related_name="participant_answers"
    )
    selected_options = models.ManyToManyField(AnswerOption, blank=True)  # For MCQ types
    selected_answer_bool = models.BooleanField(null=True, blank=True)  # For True/False

    # Nullable initially, set after submission based on determine_correctness
    is_correct = models.BooleanField(null=True, blank=True)

    class Meta:
        # Ensure a user cannot answer the same question twice in one attempt
        constraints = [
            UniqueConstraint(
                fields=["attempt", "question"], name="unique_participant_answer"
            )
        ]

    def determine_correctness(self):
        """
        Determines if the participant's answer is correct based on the question type
        and selected options/boolean. Sets the `is_correct` field.
        """
        correct = False
        question_type = self.question.question_type

        if (
            question_type == QuestionTypes.SINGLE_MCQ
            or question_type == QuestionTypes.MULTI_MCQ
        ):
            # Get the IDs of correct options for the question
            correct_option_ids = set(
                self.question.answer_options.filter(is_correct=True).values_list(
                    "id", flat=True
                )
            )
            # Get the IDs of options selected by the participant
            selected_option_ids = set(
                self.selected_options.values_list("id", flat=True)
            )

            if question_type == QuestionTypes.SINGLE_MCQ:
                # For Single MCQ, correct if exactly one option is selected AND that option is the correct one.
                # Also, if no option is selected and there are no correct options (edge case, likely invalid quiz design but handle defensively)
                # Or if no option is selected and there IS a correct option (incorrect).
                # Let's assume valid quiz design where there is exactly one correct option for SINGLE_MCQ.
                if len(correct_option_ids) == 1 and len(selected_option_ids) == 1:
                    correct = selected_option_ids == correct_option_ids
                elif len(correct_option_ids) > 0 and len(selected_option_ids) == 0:
                    correct = (
                        False  # No answer selected for an MCQ with a correct option
                    )
                elif len(correct_option_ids) == 0 and len(selected_option_ids) == 0:
                    correct = True  # No correct option, no selected option (weird, but technically correct match)
                else:  # Any other combination is incorrect
                    correct = False

            elif question_type == QuestionTypes.MULTI_MCQ:
                # For Multi MCQ, correct if the set of selected options exactly matches the set of correct options.
                correct = selected_option_ids == correct_option_ids

        elif question_type == QuestionTypes.TRUE_FALSE:
            # Correct if the selected boolean matches the correct boolean for the question.
            # Need to handle the case where selected_answer_bool or correct_answer_bool is None.
            # Assume if either is None, it's incorrect or unanswerable. Let's treat None as incorrect unless both are None.
            if (
                self.selected_answer_bool is not None
                and self.question.correct_answer_bool is not None
            ):
                correct = self.selected_answer_bool == self.question.correct_answer_bool
            elif (
                self.selected_answer_bool is None
                and self.question.correct_answer_bool is None
            ):
                correct = True  # Weird case, but matching None to None
            else:
                correct = False  # One is None, the other isn't

        self.is_correct = correct
        self.save()  # Save the correctness status

        return self.is_correct

    def __str__(self):
        return f"Answer for Q: {self.question.text[:30]}..."
