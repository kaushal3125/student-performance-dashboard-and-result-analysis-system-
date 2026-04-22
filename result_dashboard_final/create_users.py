from django.contrib.auth.models import User
from results.models import UserProfile

def create_user(username, password, role, roll_no=None):
    if not User.objects.filter(username=username).exists():
        user = User.objects.create_user(username=username, password=password)
        UserProfile.objects.create(user=user, role=role, roll_no=roll_no)
        print(f"Created {role} user: {username}")
    else:
        print(f"User {username} already exists.")

# Create Admin
create_user('admin_user', 'password123', 'ADMIN')

# Create Faculty
create_user('faculty_user', 'password123', 'FACULTY')

# Create Student matching an existing roll_no (e.g., MCA001 from sample data)
create_user('student_mca001', 'password123', 'STUDENT', 'MCA001')
create_user('student_mca002', 'password123', 'STUDENT', 'MCA002')

print("User creation complete.")
