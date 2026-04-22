from django.db import models
from django.contrib.auth.models import User

class UserProfile(models.Model):
    ROLE_CHOICES = (
        ('ADMIN', 'Admin'),
        ('FACULTY', 'Faculty'),
        ('STUDENT', 'Student'),
    )
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='STUDENT')
    roll_no = models.CharField(max_length=20, blank=True, null=True, help_text="Required for students to link their results")

    def __str__(self):
        return f"{self.user.username} - {self.role}"

class StudentResult(models.Model):
    name = models.CharField(max_length=100)
    roll_no = models.CharField(max_length=20)
    subject = models.CharField(max_length=100)
    marks = models.IntegerField()
    max_marks = models.IntegerField(default=100)
    semester = models.IntegerField()
    batch = models.CharField(max_length=20)

    def __str__(self):
        return f"{self.roll_no} - {self.name} ({self.subject})"

    @property
    def percentage(self):
        if self.max_marks:
            return round((self.marks / self.max_marks) * 100, 2)
        return 0

    @property
    def is_pass(self):
        return self.marks >= 40
