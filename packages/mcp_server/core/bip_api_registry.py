# packages/mcp_server/core/bip_api_registry.py
from typing import List, Dict, TypedDict

class ApiEndpointInfo(TypedDict):
    path: str
    description: str
    data_schema_hint: str # Optional but helpful for the LLM

# Categorized API Endpoints
# This structure can be used to generate a flat list for the LLM prompt if needed,
# or for a future multi-stage LLM selection process.

BIP_API_CATEGORIES: Dict[str, List[ApiEndpointInfo]] = {
    "Academics": [
        {
            "path": "/nova-api/academic-course-faculty-mappings",
            "description": "Shows faculty assigned to the courses the logged-in student is enrolled in for specific departments, semesters, and academic years. Best for questions like 'Who teaches my [Course Name] course?', 'Which faculties are teaching me this semester?', or 'List my current course faculty'. Also useful for general queries like 'Who teaches [Course Name] to [Department] students?'.",
            "data_schema_hint": "Returns a list of course-faculty mapping records relevant to the student or query. Key fields include 'id', 'faculties' (faculty details string), 'academic_courses' (course details string), 'academic_years' (year string), 'student_department_id' (list of department IDs), 'student_semester', 'status'."
        },
        {
            "path": "/nova-api/academic-feedbacks",
            "description": "Provides a list of academic feedback items submitted by or for the user. Useful for questions about feedback received, feedback status, feedback content, or feedback for specific courses or assessment periods (e.g., PT1, PT2).",
            "data_schema_hint": "Returns a list of feedback objects, each typically containing 'id', 'students' (student identifier string), 'academic_course_faculty_mappings' (course and faculty info string), 'periodical_statuses' (e.g., PT1, PT2), 'faculty_message', 'topic_discussions', 'course_related_activities', 'syllabus_coverage', 'overall_satisfication_level', 'general_comments'."
        },
        {
            "path": "/nova-api/periodical-statuses",
            "description": "Provides information about the status of periodical assessments like PT1, PT2, Model Exams, and Semester Exams for various semesters. Useful for questions like 'What is the status of PT1 for semester 3?', 'Are semester exams active?', or 'List all periodical tests for the current semester'.",
            "data_schema_hint": "Returns a list of periodical status objects. Key fields likely include 'id', 'periodical_name' (e.g., PT1, SEMESTER EXAM), 'semester', 'status' (e.g., Active, Completed, Upcoming), 'start_date', 'end_date'."
        }
    ],
    "Master Entries": [
        {
            "path": "/nova-api/departments", # Integrated
            "description": "Provides a list of all academic departments and their internal IDs. Useful for mapping department names to IDs for filtering other resources.",
            "data_schema_hint": "Returns a list of department objects, each with 'id' (e.g., value: 31) and 'name' (e.g., value: 'Artificial Intelligence and Machine Learning')."
        },
        # {
        #     "path": "/nova-api/academic-years",
        #     "description": "Lists academic years (e.g., 2023-2024). Useful for filtering data by academic session.",
        #     "data_schema_hint": "List of academic year objects, likely with 'id' and 'year_name' or 'range'."
        # },
        # {
        #     "path": "/nova-api/designations",
        #     "description": "Lists faculty or staff designations.",
        #     "data_schema_hint": "List of designation objects, likely with 'id' and 'designation_name'."
        # },
        # {
        #     "path": "/nova-api/student-statuses",
        #     "description": "Lists possible student statuses (e.g., Active, Inactive, Graduated).",
        #     "data_schema_hint": "List of status objects, likely with 'id' and 'status_name'."
        # },
        # {
        #     "path": "/nova-api/faculty-statuses",
        #     "description": "Lists possible faculty statuses.",
        #     "data_schema_hint": "List of status objects, likely with 'id' and 'status_name'."
        # }
    ],
    "People": [
        {
            "path": "/nova-api/students", # Integrated
            "description": "Provides detailed individual student profile information. This is the primary endpoint for looking up a specific student's details using identifiers like name, roll number, or registration/enrollment number. It can also list students, potentially filtered by department ID. Useful for questions such as 'What is the name of student with roll number X?', 'Find student [NAME]', 'List students in [DEPARTMENT NAME]', or 'What is my department?'. This endpoint does NOT directly describe relationships between different students.",
            "data_schema_hint": "Returns a list of student objects (or a single object if fetched by ID). Each student object contains 'id', 'name', 'roll_no', 'enroll_no', 'email', 'department', 'batch', 'semester', etc."
        },
        {
            "path": "/nova-api/faculties",
            "description": "Provides detailed individual faculty profile information. Use this to look up a specific faculty's details using identifiers like name or employee ID.",
            "data_schema_hint": "Returns a list of faculty objects (or a single object if fetched by ID). Each faculty object typically contains 'id', 'name', 'employee_id', 'department', 'designation', 'email', etc."
        },
        # {
        #     "path": "/nova-api/mentors",
        #     "description": "Information about student mentors and their mentees.",
        #     "data_schema_hint": "Data related to mentor-mentee assignments."
        # }
    ],
    "Student Achievements": [
        {
            "path": "/nova-api/student-activity-masters", # Integrated
            "description": "Provides a list of available student activities, events, workshops, hackathons, and competitions (including technical competitions, paper presentations, etc.) recognized by the college. Useful for finding events by name, type (e.g., 'technical competition'), category, organizer, or location. Includes details like event name, organizer, dates, location, registration links, and rewards eligibility.",
            "data_schema_hint": "Returns a list of event objects. Key fields include 'id', 'event_name', 'event_code', 'organizer', 'web_url', 'event_category' (e.g., 'Competition', 'Paper Presentation', 'Hackathon'), 'status', 'start_date', 'end_date', 'location', 'event_level', 'rewards_eligible'."
        },
        {
            "path": "/nova-api/student-achievement-loggers", # Integrated
            "description": "Retrieves the logged-in student's personal record of achievements, event participations, paper presentations, and competition entries. Best for questions specifically asking for 'my achievements', 'my participations', 'my logged activities', or 'my paper presentation records'. This shows what the specific student has recorded.",
            "data_schema_hint": "Returns a list of the student's individual achievement/activity log items. Key fields include 'id', 'students' (student info), 'event_category', 'student_activity_masters' (details of the master event like name, organizer), 'from_date', 'to_date', 'mode_of_participate', 'iqac_verification' (status like Approved, Initiated)."
        }
        # Add other achievement-related APIs here as they are integrated:
        # /nova-api/student-paper-presentation-reports
        # /nova-api/student-project-presentation-reports
        # ...and so on for internships, patents, etc.
    ]
    # Add other categories like "Projects", "SSIG", "Special Labs", "Student Action Plans", 
    # "Student Declarations", "TAC", "Users" as APIs from those categories are integrated.
}

# Flattened list for the LLM prompt (backward compatibility with current llm_service.py)
BIP_API_ENDPOINTS: List[ApiEndpointInfo] = [
    endpoint for category_apis in BIP_API_CATEGORIES.values() for endpoint in category_apis
]

# Add placeholder entries for APIs not yet fully described but mentioned in the user's context
# This helps the Path Selection LLM know they exist, even if we can't fully handle them yet.
# These would be gradually replaced with full entries in BIP_API_CATEGORIES.
_placeholder_paths = [
    # Master Entries
    "/nova-api/academic-years", "/nova-api/designations", "/nova-api/student-statuses", "/nova-api/faculty-statuses",
    # Mentors
    "/nova-api/mentors",
    # People
    "/nova-api/faculties",
    # Projects
    "/nova-api/student-project-details", "/nova-api/student-project-registrations", "/nova-api/student-project-implementation-details",
    # SSIG
    "/nova-api/ssigs",
    # Special Labs
    "/nova-api/special-labs", "/nova-api/special-labs-details",
    # Student Achievements (continued)
    "/nova-api/student-paper-presentation-reports", "/nova-api/student-project-presentation-reports",
    "/nova-api/student-project-outcomes", "/nova-api/student-technical-competition-reports",
    "/nova-api/mba-student-technical-competitions", "/nova-api/student-patent-trackers",
    "/nova-api/student-patent-reports", "/nova-api/industries", "/nova-api/student-internships",
    "/nova-api/internships-trackers", "/nova-api/internships-reports",
    # Student Action Plans
    "/nova-api/student-action-plan-internships", "/nova-api/student-action-plan-online-courses",
    "/nova-api/student-action-plan-paper-presentations", "/nova-api/student-action-plan-patents",
    "/nova-api/student-action-plan-products", "/nova-api/student-action-plan-project-presentations",
    "/nova-api/student-action-plan-competitions",
    # Student Declarations
    "/nova-api/student-declarations",
    # TAC
    "/nova-api/student-tacs", "/nova-api/student-tac-review-appoinments", "/nova-api/tac-internship-projects",
    # Users
    "/nova-api/users"
]

_existing_paths_in_flat_list = {ep["path"] for ep in BIP_API_ENDPOINTS}
for p_path in _placeholder_paths:
    if p_path not in _existing_paths_in_flat_list:
        BIP_API_ENDPOINTS.append({
            "path": p_path,
            "description": f"API endpoint for {p_path.split('/')[-1].replace('-', ' ')}. Details to be added.", # Generic description
            "data_schema_hint": "Specific schema to be defined."
        })


def get_api_endpoint_by_path(path: str) -> ApiEndpointInfo | None:
    # Search in the flattened list for now
    for endpoint in BIP_API_ENDPOINTS:
        if endpoint["path"] == path:
            return endpoint
    return None
