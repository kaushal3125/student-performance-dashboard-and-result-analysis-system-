import csv
import json
import logging
from collections import defaultdict

from django.shortcuts import render, redirect
from django.http import HttpResponse, HttpResponseServerError, FileResponse, Http404
import os
from django.conf import settings
from django.db.models import Avg, Count, Max, Min, Q, StdDev, Variance
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.contrib import messages

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter

from .models import StudentResult, UserProfile

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helper: get profile or default
# ---------------------------------------------------------------------------
def _get_user_role(user):
    if user.is_superuser:
        return 'ADMIN', None
    try:
        profile = user.profile
        return profile.role, profile.roll_no
    except Exception:
        return 'STUDENT', None

# ---------------------------------------------------------------------------
# Helper: apply filters from GET params
# ---------------------------------------------------------------------------
def _apply_filters(request, queryset, role, user_roll_no):
    try:
        # Enforce role-based data isolation
        if role == 'STUDENT' and user_roll_no:
            queryset = queryset.filter(roll_no=user_roll_no)

        semester = request.GET.get('semester', '').strip()
        subject = request.GET.get('subject', '').strip()
        batch = request.GET.get('batch', '').strip()
        search = request.GET.get('search', '').strip()

        if semester:
            queryset = queryset.filter(semester=semester)
        if subject:
            queryset = queryset.filter(subject=subject)
        if batch:
            queryset = queryset.filter(batch=batch)
        if search:
            queryset = queryset.filter(Q(name__icontains=search) | Q(roll_no__icontains=search))

        return queryset, semester, subject, batch, search
    except Exception as e:
        logger.error(f"Error applying filters: {e}")
        return queryset, '', '', '', ''


# ---------------------------------------------------------------------------
# Helper: get career recommendation
# ---------------------------------------------------------------------------
def get_career_recommendation(subjects_data):
    if not subjects_data:
        return {"career": "N/A", "focus_topics": "N/A", "interview_questions": "N/A"}
    
    # Sort subjects by marks descending
    sorted_subjects = sorted(subjects_data, key=lambda x: x['marks'], reverse=True)
    top_subject = sorted_subjects[0]['name'].lower()
    
    # Logic mapping
    if any(keyword in top_subject for keyword in ['math', 'stat', 'data']):
        return {
            "career": "Data Analyst / Data Scientist",
            "focus_topics": "Probability, Machine Learning, Data Visualization",
            "interview_questions": "Explain p-value. How do you handle missing data? Describe a Random Forest."
        }
    elif any(keyword in top_subject for keyword in ['python', 'java', 'c++', 'programming', 'web', 'dbms', 'structure']):
        return {
            "career": "Software Developer",
            "focus_topics": "Data Structures, Algorithms, System Design",
            "interview_questions": "What is OOP? Explain REST API. How does a Hash Map work?"
        }
    elif any(keyword in top_subject for keyword in ['account', 'commerce', 'finance', 'econ']):
        return {
            "career": "Finance / CA",
            "focus_topics": "Financial Modeling, Risk Management, Auditing",
            "interview_questions": "What is a cash flow statement? Explain DCF valuation."
        }
    elif any(keyword in top_subject for keyword in ['theory', 'humanities', 'history', 'english']):
        return {
            "career": "Research / Teaching",
            "focus_topics": "Pedagogy, Qualitative Analysis, Public Speaking",
            "interview_questions": "How do you engage a difficult class? Explain your research methodology."
        }
    else:
        return {
            "career": "General Professional",
            "focus_topics": "Communication, Project Management, Critical Thinking",
            "interview_questions": "Describe a time you solved a complex problem."
        }


# ---------------------------------------------------------------------------
# Upload CSV
# ---------------------------------------------------------------------------
@login_required
def upload_csv(request):
    role, _ = _get_user_role(request.user)
    if role != 'ADMIN':
        messages.error(request, "Only administrators can upload data.")
        return redirect('dashboard')

    if request.method == 'POST':
        file = request.FILES.get('file')
        if not file:
            messages.error(request, "No file selected.")
        else:
            try:
                decoded = file.read().decode('utf-8').splitlines()
                reader = csv.reader(decoded)
                header = next(reader, None)
                if not header:
                    raise ValueError("CSV file is empty or missing headers.")
                
                count = 0
                for row in reader:
                    if not row or len(row) < 6:
                        continue
                    try:
                        StudentResult.objects.create(
                            name=row[0].strip(),
                            roll_no=row[1].strip(),
                            subject=row[2].strip(),
                            marks=int(row[3]),
                            semester=int(row[4]),
                            batch=row[5].strip(),
                            max_marks=int(row[6]) if len(row) > 6 else 100,
                        )
                        count += 1
                    except (ValueError, IndexError):
                        continue # Skip malformed rows
                
                messages.success(request, f'Successfully imported {count} records.')
                return redirect('dashboard')
            except Exception as e:
                logger.exception("Upload error")
                messages.error(request, f'Error processing file: {e}')
                
    return render(request, 'upload.html', {'role': role})


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@login_required
def dashboard(request):
    try:
        role, user_roll_no = _get_user_role(request.user)
        all_data = StudentResult.objects.all()

        # --- distinct filter choices (from full dataset based on access) ---
        base_data = all_data
        if role == 'STUDENT' and user_roll_no:
            base_data = base_data.filter(roll_no=user_roll_no)

        all_semesters = sorted(base_data.values_list('semester', flat=True).distinct())
        all_subjects = sorted(base_data.values_list('subject', flat=True).distinct())
        all_batches = sorted(base_data.values_list('batch', flat=True).distinct())

        # --- apply filters ---
        data, sel_semester, sel_subject, sel_batch, search_q = _apply_filters(request, all_data, role, user_roll_no)

        # Per-student aggregate for ranking and stats
        student_agg = defaultdict(lambda: {'name': '', 'total': 0, 'count': 0, 'max': 0, 'pass': 0, 'subjects': []})
        for rec in data:
            k = rec.roll_no
            student_agg[k]['name'] = rec.name
            student_agg[k]['total'] += rec.marks
            student_agg[k]['max'] += rec.max_marks
            student_agg[k]['count'] += 1
            student_agg[k]['subjects'].append({
                'name': rec.subject,
                'marks': rec.marks,
                'max': rec.max_marks,
                'status': 'Pass' if rec.marks >= 40 else 'Fail',
            })
            if rec.marks >= 40:
                student_agg[k]['pass'] += 1

        student_rows = []
        pass_student_count = 0
        fail_student_count = 0

        for roll, v in student_agg.items():
            avg = round(v['total'] / v['count'], 2) if v['count'] else 0
            pct = round((v['total'] / v['max']) * 100, 2) if v['max'] else 0
            failed_subjects = v['count'] - v['pass']
            status = 'Pass' if failed_subjects == 0 else 'Fail'
            if status == 'Pass': pass_student_count += 1
            else: fail_student_count += 1

            sorted_subs = sorted(v['subjects'], key=lambda x: x['marks'], reverse=True)
            strengths = [s['name'] for s in sorted_subs[:2]] if sorted_subs else []
            weaknesses = [s['name'] for s in sorted_subs[-2:]] if len(sorted_subs) > 1 else []
            career_dict = get_career_recommendation(v['subjects'])

            subj_json = json.dumps([{
                'subject': s['name'],
                'marks': s['marks'],
                'max': s['max'],
                'status': s['status']
            } for s in v['subjects']])

            student_rows.append({
                'roll_no': roll,
                'name': v['name'],
                'avg': avg,
                'percentage': pct,
                'status': status,
                'subjects': v['subjects'],
                'subjects_json': subj_json,
                'strengths': strengths,
                'weaknesses': weaknesses,
                'career_recommendation': career_dict['career'],
                'focus_topics': career_dict['focus_topics'],
                'interview_questions': career_dict['interview_questions'],
            })
        
        # Sort for ranking
        student_rows.sort(key=lambda x: x['percentage'], reverse=True)
        
        # Assign ranks
        for i, row in enumerate(student_rows):
            row['rank'] = i + 1

        total_students = len(student_rows)
        pass_pct = round((pass_student_count / total_students) * 100, 1) if total_students else 0
        fail_pct = round((fail_student_count / total_students) * 100, 1) if total_students else 0

        topper_name = student_rows[0]['name'] if student_rows else 'N/A'
        topper_marks = f"{student_rows[0]['percentage']}%" if student_rows else '0%'
        topper_roll = student_rows[0]['roll_no'] if student_rows else '-'

        # Fix Top/Bottom 5 logic
        top_5 = student_rows[:5]
        bottom_5 = student_rows[-5:] if total_students > 5 else student_rows[1:] # If <= 5, bottom is anything except #1

        # Subject analytics
        subject_stats = (
            data.values('subject')
            .annotate(
                avg=Avg('marks'), 
                highest=Max('marks'),
                lowest=Min('marks'),
                total_cnt=Count('id'),
                std_dev=StdDev('marks'),
                variance=Variance('marks')
            )
            .order_by('subject')
        )
        
        subject_labels = []
        subject_avgs = []
        subject_analytics = []

        for s in subject_stats:
            sub_name = s['subject']
            sub_pass = data.filter(subject=sub_name, marks__gte=40).count()
            sub_pct = round((sub_pass / s['total_cnt']) * 100, 1) if s['total_cnt'] else 0
            
            # Calculate median
            sub_marks = list(data.filter(subject=sub_name).values_list('marks', flat=True).order_by('marks'))
            median = 0
            if sub_marks:
                mid = len(sub_marks) // 2
                if len(sub_marks) % 2 == 0:
                    median = (sub_marks[mid - 1] + sub_marks[mid]) / 2.0
                else:
                    median = sub_marks[mid]
            
            subject_labels.append(sub_name)
            subject_avgs.append(round(s['avg'], 2) if s['avg'] else 0)
            
            subject_analytics.append({
                'subject': sub_name,
                'avg': round(s['avg'], 2) if s['avg'] else 0,
                'high': s['highest'],
                'low': s['lowest'],
                'pass_pct': sub_pct,
                'median': round(median, 2),
                'std_dev': round(s['std_dev'], 2) if s['std_dev'] else 0,
                'variance': round(s['variance'], 2) if s['variance'] else 0,
            })

        # Semester Chart
        sem_stats = (
            data.values('semester')
            .annotate(avg=Avg('marks'))
            .order_by('semester')
        )
        sem_labels = [f"Sem {x['semester']}" for x in sem_stats]
        sem_data = [round(x['avg'], 2) if x['avg'] else 0 for x in sem_stats]

        # Line chart for top students
        top10 = student_rows[:10]
        line_labels = [r['name'] for r in top10]
        line_data = [r['percentage'] for r in top10]

        # For comparison feature frontend
        all_students_for_json = []
        for r in student_rows:
            all_students_for_json.append({
                'roll_no': r['roll_no'],
                'name': r['name'],
                'percentage': r['percentage'],
                'subjects': r['subjects']
            })

        # Topper graph
        topper_labels = []
        topper_data = []
        for sa in subject_analytics:
            topper_labels.append(sa['subject'])
            topper_data.append(sa['high'])

        # Performance distribution graph
        dist_ranges = {'<40%': 0, '40-60%': 0, '60-80%': 0, '>80%': 0}
        for r in student_rows:
            if r['percentage'] < 40: dist_ranges['<40%'] += 1
            elif r['percentage'] < 60: dist_ranges['40-60%'] += 1
            elif r['percentage'] < 80: dist_ranges['60-80%'] += 1
            else: dist_ranges['>80%'] += 1

        # Scatter Chart Data (Score vs Percentage)
        scatter_data = []
        for r in student_rows:
            # We can use avg or total marks. We have `avg` and `percentage`. Let's plot avg vs percentage.
            scatter_data.append({'x': r['avg'], 'y': r['percentage'], 'name': r['name']})

        # Pagination
        paginator = Paginator(student_rows, 10)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        
        # Clean query string for pagination links
        query_params = request.GET.copy()
        if 'page' in query_params:
            del query_params['page']
        query_string = query_params.urlencode()

        context = {
            'role': role,
            'user': request.user,
            'all_semesters': all_semesters,
            'all_subjects': all_subjects,
            'all_batches': all_batches,
            'sel_semester': sel_semester,
            'sel_subject': sel_subject,
            'sel_batch': sel_batch,
            'search_q': search_q,
            'total': total_students,
            'pass_count': pass_student_count,
            'fail_count': fail_student_count,
            'pass_pct': pass_pct,
            'fail_pct': fail_pct,
            'topper_name': topper_name,
            'topper_marks': topper_marks,
            'topper_roll': topper_roll,
            'top_5': top_5,
            'bottom_5': bottom_5,
            'subject_analytics': subject_analytics,
            'subject_labels_json': json.dumps(subject_labels),
            'subject_avgs_json': json.dumps(subject_avgs),
            'pass_fail_json': json.dumps([pass_student_count, fail_student_count]),
            'line_labels_json': json.dumps(line_labels),
            'line_data_json': json.dumps(line_data),
            'sem_labels_json': json.dumps(sem_labels),
            'sem_data_json': json.dumps(sem_data),
            'all_students_json': json.dumps(all_students_for_json),
            'topper_labels_json': json.dumps(topper_labels),
            'topper_data_json': json.dumps(topper_data),
            'dist_labels_json': json.dumps(list(dist_ranges.keys())),
            'dist_data_json': json.dumps(list(dist_ranges.values())),
            'scatter_data_json': json.dumps(scatter_data),
            'query_string': query_string,
            'page_obj': page_obj,
        }
        return render(request, 'dashboard.html', context)
    except Exception as e:
        logger.exception("Dashboard error")
        return HttpResponseServerError(f"An internal error occurred: {e}")


# ---------------------------------------------------------------------------
# Export CSV
# ---------------------------------------------------------------------------
@login_required
def export_csv(request):
    try:
        role, user_roll_no = _get_user_role(request.user)
        data, *_ = _apply_filters(request, StudentResult.objects.all(), role, user_roll_no)

        if not data.exists():
            messages.warning(request, "No data available to export.")
            return redirect('dashboard')

        # Ranks
        student_agg = defaultdict(lambda: {'name': '', 'total': 0, 'count': 0, 'max': 0, 'pass': 0})
        for rec in data:
            k = rec.roll_no
            student_agg[k]['total'] += rec.marks
            student_agg[k]['max'] += rec.max_marks
        
        student_rows = [{'roll_no': roll, 'percentage': round((v['total']/v['max'])*100, 2) if v['max'] else 0} for roll, v in student_agg.items()]
        student_rows.sort(key=lambda x: x['percentage'], reverse=True)
        ranks = {row['roll_no']: i+1 for i, row in enumerate(student_rows)}

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="student_report.csv"'

        writer = csv.writer(response)
        writer.writerow(['Rank', 'Roll No', 'Name', 'Subject', 'Marks', 'Max Marks', 'Percentage', 'Status', 'Semester', 'Batch'])
        
        for rec in data.order_by('roll_no', 'subject'):
            pct = round((rec.marks / rec.max_marks) * 100, 2) if rec.max_marks else 0
            rank = ranks.get(rec.roll_no, '-')
            writer.writerow([
                rank, rec.roll_no, rec.name, rec.subject,
                rec.marks, rec.max_marks, pct,
                'Pass' if rec.marks >= 40 else 'Fail',
                rec.semester, rec.batch,
            ])
        return response
    except Exception as e:
        logger.exception("CSV export error")
        messages.error(request, f"Export failed: {e}")
        return redirect('dashboard')


# ---------------------------------------------------------------------------
# Export PDF
# ---------------------------------------------------------------------------
@login_required
def export_pdf(request):
    try:
        role, user_roll_no = _get_user_role(request.user)
        data, sel_semester, sel_subject, sel_batch, search_q = _apply_filters(request, StudentResult.objects.all(), role, user_roll_no)

        if not data.exists():
            messages.warning(request, "No data available to export.")
            return redirect('dashboard')

        # Ranks
        student_agg = defaultdict(lambda: {'name': '', 'total': 0, 'count': 0, 'max': 0, 'pass': 0})
        for rec in data:
            k = rec.roll_no
            student_agg[k]['total'] += rec.marks
            student_agg[k]['max'] += rec.max_marks
        
        student_rows = [{'roll_no': roll, 'percentage': round((v['total']/v['max'])*100, 2) if v['max'] else 0} for roll, v in student_agg.items()]
        student_rows.sort(key=lambda x: x['percentage'], reverse=True)
        ranks = {row['roll_no']: i+1 for i, row in enumerate(student_rows)}

        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="student_report.pdf"'

        doc = SimpleDocTemplate(response, pagesize=letter)
        styles = getSampleStyleSheet()
        elements = []

        elements.append(Paragraph('Student Performance Report', styles['Title']))
        elements.append(Spacer(1, 12))

        # Filter info
        filters_text = []
        if sel_semester: filters_text.append(f'Semester: {sel_semester}')
        if sel_subject: filters_text.append(f'Subject: {sel_subject}')
        if sel_batch: filters_text.append(f'Batch: {sel_batch}')
        if search_q: filters_text.append(f'Search: {search_q}')
        
        if filters_text:
            elements.append(Paragraph('Filters: ' + ' | '.join(filters_text), styles['Normal']))
            elements.append(Spacer(1, 8))

        # Summary
        total_students = len(student_rows)
        pass_count = sum(1 for s in student_rows if s['percentage'] >= 40) # Simple pass logic
        elements.append(Paragraph(f"Summary: Total Students: {total_students} | Overall Pass Rate: {round((pass_count/total_students)*100, 1) if total_students else 0}%", styles['Normal']))
        elements.append(Spacer(1, 12))

        # Table
        table_data = [['Rank', 'Roll No', 'Name', 'Subject', 'Marks', '%', 'Status', 'Sem']]
        for rec in data.order_by('roll_no', 'subject'):
            pct = round((rec.marks / rec.max_marks) * 100, 1) if rec.max_marks else 0
            rank = ranks.get(rec.roll_no, '-')
            table_data.append([
                rank, rec.roll_no, rec.name, rec.subject,
                f"{rec.marks}/{rec.max_marks}", pct,
                'Pass' if rec.marks >= 40 else 'Fail',
                rec.semester
            ])

        tbl = Table(table_data, repeatRows=1)
        tbl.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4f46e5')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.grey),
            ('ALIGN', (4, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(tbl)

        doc.build(elements)
        return response
    except Exception as e:
        logger.exception("PDF export error")
        messages.error(request, f"Export failed: {e}")
        return redirect('dashboard')

# ---------------------------------------------------------------------------
# Download Sample CSV
# ---------------------------------------------------------------------------
@login_required
def download_sample(request):
    file_path = os.path.join(settings.BASE_DIR, 'sample_data.csv')
    if os.path.exists(file_path):
        return FileResponse(open(file_path, 'rb'), as_attachment=True, filename='sample_data.csv')
    raise Http404("Sample file not found")
