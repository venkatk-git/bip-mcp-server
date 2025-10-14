# packages/mcp_server/core/bip_api_registry.py
"""
BIP API Registry - Centralized registry of all available BIP API endpoints
with detailed descriptions and schema hints for intelligent routing.
"""
from typing import List, Dict, TypedDict

class ApiEndpointInfo(TypedDict):
    """Type definition for API endpoint information."""
    path: str
    description: str
    data_schema_hint: str
    category: str  # New field for better organization

# Categorized API Endpoints for Intelligent Routing
# Organized by functional area to improve AI path selection accuracy

BIP_API_CATEGORIES: Dict[str, List[ApiEndpointInfo]] = {
    "Academics": [
        {
            "path": "/nova-api/academic-course-faculty-mappings",
            "description": "Faculty-course assignments and teaching schedules. Use for questions about 'who teaches [COURSE]', 'my current teachers', 'faculty teaching me this semester', or course-faculty relationships. NOT for individual faculty profile details.",
            "data_schema_hint": "Course-faculty mapping objects with 'faculties', 'academic_courses', 'student_department_id', 'student_semester', 'academic_years', 'status'.",
            "category": "Academics"
        },
        {
            "path": "/nova-api/academic-feedbacks",
            "description": "Academic feedback and evaluations. Use for questions about course feedback, faculty feedback, assessment feedback, or feedback for specific periods (PT1, PT2, semester).",
            "data_schema_hint": "Feedback objects with 'students', 'academic_course_faculty_mappings', 'periodical_statuses', 'faculty_message', 'topic_discussions', 'syllabus_coverage', 'overall_satisfication_level'.",
            "category": "Academics"
        },
        {
            "path": "/nova-api/periodical-statuses",
            "description": "Periodical assessment and exam status tracking. Use for questions about exam schedules, test availability, PT1/PT2/Model/Semester exam status, semester-wise assessment calendar, or current exam periods. Supports filtering by periodical type, semester, and status.",
            "data_schema_hint": "Periodical status objects with 'periodical_name' (PT1, PT2, Model Exam, Semester Exam), 'semester', 'status' (Active, Completed, Upcoming, etc.), 'start_date', 'end_date', and related metadata.",
            "category": "Academics"
        }
    ],
    "Master Entries": [
        {
            "path": "/nova-api/departments",
            "description": "All academic departments and their IDs. Use for department listing, department information, or as reference for filtering other resources by department.",
            "data_schema_hint": "Department objects with 'id' and 'name' fields.",
            "category": "Master Entries"
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
            "path": "/nova-api/students",
            "description": "Student profiles and information. Primary endpoint for student lookup by name, roll number, or enrollment number. Supports department-based filtering for listing students. Use for 'who is', 'find student', 'student details', or 'students in department'.",
            "data_schema_hint": "Student objects with 'id', 'name', 'roll_no', 'enroll_no', 'email', 'department', 'batch', 'semester'.",
            "category": "People"
        },
        {
            "path": "/nova-api/faculties",
            "description": "Individual faculty profiles and personal details. Use for questions about specific faculty members like 'faculty ID of [NAME]', 'employee ID of [NAME]', 'who is [FACULTY NAME]', faculty contact information, or faculty department/designation details.",
            "data_schema_hint": "Faculty objects with 'id', 'name', 'employee_id', 'department', 'designation', 'email'.",
            "category": "People"
        },
        # {
        #     "path": "/nova-api/mentors",
        #     "description": "Information about student mentors and their mentees.",
        #     "data_schema_hint": "Data related to mentor-mentee assignments."
        # }
    ],
    "Student Activities": [
        {
            "path": "/nova-api/student-activity-masters",
            "description": "College events, activities, and competitions catalog. Use for finding events by name, type (hackathon, competition, workshop), category, organizer, or location. Includes event details, dates, and eligibility information.",
            "data_schema_hint": "Event objects with 'event_name', 'event_code', 'organizer', 'web_url', 'event_category', 'status', 'start_date', 'end_date', 'location', 'rewards_eligible'.",
            "category": "Student Activities"
        },
        {
            "path": "/nova-api/student-achievement-loggers",
            "description": "Personal student achievement records. Use specifically for 'my achievements', 'my participations', 'my activities', or personal accomplishment tracking. Shows individual student's recorded activities and their verification status.",
            "data_schema_hint": "Achievement log objects with 'students', 'event_category', 'student_activity_masters', 'from_date', 'to_date', 'mode_of_participate', 'iqac_verification'.",
            "category": "Student Activities"
        }
    ],
    "Student Reports": [
        {
            "path": "/nova-api/student-paper-presentation-reports",
            "description": "Student paper presentation records and reports. Use for questions about paper presentations, research papers, conference presentations, publication status, or academic paper verification. Includes paper titles, presentation dates, and IQAC verification.",
            "data_schema_hint": "Paper presentation objects with 'student_achievement_loggers', 'paper_title', 'start_date', 'end_date', 'status', 'original_proof_name', 'attested_proof_name', 'iqac_verification', 'created_at'.",
            "category": "Student Reports"
        },
        {
            "path": "/nova-api/student-project-competition-reports",
            "description": "Student project competition participation reports. Use for questions about project competitions, hackathons, innovation contests, project showcases, or competition achievements. Tracks project-based competitive activities.",
            "data_schema_hint": "Project competition objects with 'student_achievement_loggers', 'project_title', 'from_date', 'to_date', 'iqac_verification', 'created_at'.",
            "category": "Student Reports"
        },
        {
            "path": "/nova-api/student-technical-competition-reports",
            "description": "Student technical competition participation and achievements. Use for questions about coding competitions, technical contests, hackathons, tech events, sponsorship details, or competition results. Includes participation type and winning proofs.",
            "data_schema_hint": "Technical competition objects with 'student_achievement_loggers', 'event_title', 'participated_as', 'from_date', 'to_date', 'sponsorship_types', 'status', 'winning_proof_name', 'original_proof_name', 'attested_proof_name', 'iqac_verification', 'created_at'.",
            "category": "Student Reports"
        },
        {
            "path": "/nova-api/internship-reports",
            "description": "Student internship experiences and reports. Use for questions about internships, industry experience, work placements, company details, stipend information, or internship verification. Includes company location, sector, and AICTE recognition status.",
            "data_schema_hint": "Internship objects with 'internship_trackers', 'year_of_study', 'ssigs', 'special_labs', 'sector', 'address_line_1', 'address_line_2', 'city', 'state', 'postal_code', 'country', 'industry_website', 'industry_contact_details', 'referred_by', 'stipend_amount', 'is_aicte', 'full_document_name', 'original_proof_name', 'attested_proof_name', 'iqac_verification', 'created_at'.",
            "category": "Student Reports"
        },
        {
            "path": "/nova-api/student-online-courses",
            "description": "Student online course enrollments and certifications. Use for questions about online courses, certifications, course completion, exam dates, course exemptions, or digital learning activities. Includes course types, marks, and sponsorship details.",
            "data_schema_hint": "Online course objects with 'students', 'year_of_study', 'special_labs', 'online_course', 'course_type', 'project_outcome', 'other_course_name', 'marks_available', 'course_exemption', 'course_start_date', 'course_end_date', 'exam_date', 'other_sponsorship_name', 'original_proof_name', 'attested_proof_name', 'iqac_verification', 'created_at'.",
            "category": "Student Reports"
        }
    ],
    "Projects": [
        {
            "path": "/nova-api/student-project-implementation-details",
            "description": "Student project implementation progress and tracking details. Use for questions about project work progress, weekly updates, project guide verification, implementation status, or project timeline tracking. Includes work carried out, guide comments, and verification status.",
            "data_schema_hint": "Project implementation objects with 'student_project_details', 'academic_years', 'semester', 'week', 'work_carried_out', 'project_guide_verification', 'verified_date', 'guide_comments', 'created_at'.",
            "category": "Projects"
        }
        # Add other project-related APIs here as they are integrated:
        # /nova-api/student-project-details
        # /nova-api/student-project-registrations
        # /nova-api/student-project-presentation-reports
        # ...and so on for other project APIs
    ]
    # Add other categories like "SSIG", "Special Labs", "Student Action Plans", 
    # "Student Declarations", "TAC", "Users" as APIs from those categories are integrated.
}

# Flattened list for LLM prompt with enhanced metadata
BIP_API_ENDPOINTS: List[ApiEndpointInfo] = []
for category_name, endpoints in BIP_API_CATEGORIES.items():
    for endpoint in endpoints:
        enhanced_endpoint = endpoint.copy()
        if "category" not in enhanced_endpoint:
            enhanced_endpoint["category"] = category_name
        BIP_API_ENDPOINTS.append(enhanced_endpoint)

# Placeholder entries for future API integration
# These provide basic awareness for the LLM until full implementation
PLACEHOLDER_APIS = [
    # Master Entries
    "/nova-api/academic-years", "/nova-api/designations", "/nova-api/student-statuses", "/nova-api/faculty-statuses",
    # Mentors
    "/nova-api/mentors",
    # People
    "/nova-api/faculties",
    # Projects
    "/nova-api/student-project-details", "/nova-api/student-project-registrations",
    # SSIG
    "/nova-api/ssigs",
    # Special Labs
    "/nova-api/special-labs", "/nova-api/special-labs-details",
    # Student Achievements (continued)
    "/nova-api/student-project-presentation-reports",
    "/nova-api/student-project-outcomes", "/nova-api/mba-student-technical-competitions", 
    "/nova-api/student-patent-trackers", "/nova-api/student-patent-reports", "/nova-api/industries", 
    "/nova-api/student-internships", "/nova-api/internships-trackers",
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

_existing_paths = {ep["path"] for ep in BIP_API_ENDPOINTS}
for p_path in PLACEHOLDER_APIS:
    if p_path not in _existing_paths:
        resource_name = p_path.split('/')[-1].replace('-', ' ').title()
        BIP_API_ENDPOINTS.append({
            "path": p_path,
            "description": f"{resource_name} endpoint (implementation pending). Limited functionality available.",
            "data_schema_hint": "Schema details to be defined upon full integration.",
            "category": "Future Integration"
        })


def get_api_endpoint_by_path(path: str) -> ApiEndpointInfo | None:
    """Retrieve API endpoint information by path."""
    for endpoint in BIP_API_ENDPOINTS:
        if endpoint["path"] == path:
            return endpoint
    return None

def get_endpoints_by_category(category: str) -> List[ApiEndpointInfo]:
    """Get all endpoints in a specific category."""
    return [ep for ep in BIP_API_ENDPOINTS if ep.get("category") == category]

def get_available_categories() -> List[str]:
    """Get list of all available API categories."""
    return list(BIP_API_CATEGORIES.keys())

def search_endpoints(query: str) -> List[ApiEndpointInfo]:
    """Search endpoints by description keywords."""
    query_lower = query.lower()
    return [
        ep for ep in BIP_API_ENDPOINTS 
        if query_lower in ep["description"].lower() or query_lower in ep["path"].lower()
    ]
