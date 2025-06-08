# packages/mcp_server/core/bip_api_registry.py
from typing import List, Dict, TypedDict

class ApiEndpointInfo(TypedDict):
    path: str
    description: str
    data_schema_hint: str # Optional but helpful for the LLM

BIP_API_ENDPOINTS: List[ApiEndpointInfo] = [
    {
        "path": "/nova-api/academic-feedbacks",
        "description": "Provides a list of academic feedback items submitted by or for the user. Useful for questions about feedback received, feedback status, feedback content, or feedback for specific courses or assessment periods (e.g., PT1, PT2).",
        "data_schema_hint": "Returns a list of feedback objects, each typically containing 'id', 'students' (student identifier string), 'academic_course_faculty_mappings' (course and faculty info string), 'periodical_statuses' (e.g., PT1, PT2), 'faculty_message', 'topic_discussions', 'course_related_activities', 'syllabus_coverage', 'overall_satisfication_level', 'general_comments'."
    },
    {
        "path": "/nova-api/students", 
        "description": "Provides detailed student profile information. This is the primary endpoint for looking up student details using identifiers like student name, roll number, or registration/enrollment number. It can also be filtered by department ID. Useful for questions such as 'What is the name of student with roll number X?', 'Find student [NAME]', 'List students in [DEPARTMENT NAME]', or 'What is my department?'.",
        "data_schema_hint": "Returns a list of student objects. Each student object contains 'id', 'name', 'roll_no', 'enroll_no', 'email', 'department', 'batch', 'semester', etc."
    },
    {
        "path": "/nova-api/departments",
        "description": "Provides a list of all academic departments and their internal IDs. Useful for mapping department names to IDs for filtering other resources.",
        "data_schema_hint": "Returns a list of department objects, each with 'id' (e.g., value: 31) and 'name' (e.g., value: 'Artificial Intelligence and Machine Learning')."
    },
    {
        "path": "/nova-api/student-activity-masters",
        "description": "Provides a list of student activities and events (e.g., paper presentations, hackathons, competitions) recognized by the college. Useful for finding events by name, category, organizer, or location (e.g., 'events in KCT', 'hackathons by IEEE'). Includes details like event name, organizer, dates, location, registration links, and rewards eligibility.",
        "data_schema_hint": "Returns a list of event objects. Key fields include 'id', 'event_name', 'event_code', 'organizer', 'web_url', 'event_category', 'status', 'start_date', 'end_date', 'location', 'event_level', 'rewards_eligible'."
    }
]

def get_api_endpoint_by_path(path: str) -> ApiEndpointInfo | None:
    for endpoint in BIP_API_ENDPOINTS:
        if endpoint["path"] == path:
            return endpoint
    return None
