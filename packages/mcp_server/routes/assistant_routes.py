# packages/mcp-server/routes/assistant_routes.py
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse 
from pydantic import BaseModel
from ..core.bip_service import fetch_bip_data, get_department_id_by_name, get_student_details_from_session 
from ..core.llm_service import get_answer_from_llm, determine_api_path_from_query, extract_query_type_and_value 
from ..core.bip_api_registry import BIP_API_ENDPOINTS 
from thefuzz import fuzz # Import for fuzzy matching

from typing import List, Dict, Any, Optional
import urllib.parse
import base64 
import json
import asyncio # For gather
import re

router = APIRouter()

async def smart_name_search(request: Request, api_path: str, search_name: str, query_details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Universal smart name search handler for any API endpoint.
    Handles name variations, partial matches, and fuzzy searching.
    
    Args:
        request: FastAPI request object
        api_path: The API endpoint to search (e.g., "/nova-api/students")
        search_name: The name to search for
        query_details: Optional query details for LLM processing
    
    Returns:
        Dict with 'success', 'data', 'message', and 'data_source' keys
    """
    print(f"Smart name search: Looking for '{search_name}' in {api_path}")
    
    # Step 1: Try exact name search
    exact_search_path = f"{api_path}?search={urllib.parse.quote(search_name)}"
    try:
        response = await fetch_bip_data(request, exact_search_path, fetch_all_pages=False)
        if response:
            data = parse_nova_api_response_data(response, resource_name_hint=exact_search_path)
            if data:
                print(f"Exact search found {len(data)} results")
                return {
                    "success": True,
                    "data": data,
                    "message": f"Found exact match for '{search_name}'",
                    "data_source": exact_search_path
                }
    except Exception as e:
        print(f"Exact search failed: {e}")
    
    # Step 2: Try partial name searches
    names = search_name.split()
    if len(names) >= 2:
        print(f"Trying partial name searches for '{search_name}'")
        
        # Try each part of the name
        for name_part in names:
            if len(name_part) >= 3:  # Only meaningful names
                partial_path = f"{api_path}?search={urllib.parse.quote(name_part)}"
                try:
                    print(f"Trying partial search: {partial_path}")
                    response = await fetch_bip_data(request, partial_path, fetch_all_pages=False)
                    if response:
                        data = parse_nova_api_response_data(response, resource_name_hint=partial_path)
                        if data:
                            # Filter results that contain multiple parts of the original name
                            filtered_results = []
                            for item in data:
                                item_name = item.get('name', '').lower()
                                # Check if item contains multiple parts of the search name
                                matches = sum(1 for name in names if name.lower() in item_name)
                                if matches >= min(2, len(names)):  # At least 2 parts or all parts if < 2
                                    filtered_results.append(item)
                            
                            if filtered_results:
                                print(f"Partial search found {len(filtered_results)} matching results")
                                return {
                                    "success": True,
                                    "data": filtered_results,
                                    "message": f"Found similar names for '{search_name}'",
                                    "data_source": f"{exact_search_path} (fallback: {partial_path})"
                                }
                except Exception as e:
                    print(f"Partial search failed for '{name_part}': {e}")
                    continue
    
    # Step 3: No results found
    return {
        "success": False,
        "data": [],
        "message": f"No records found for '{search_name}'. Please check spelling or try a different name format.",
        "data_source": exact_search_path
    }

def extract_entity_from_common_patterns(user_question: str, api_path: str) -> Optional[Dict[str, Any]]:
    """
    Generic function to extract entity names from common question patterns.
    Works across all API endpoints by detecting patterns like:
    - "Who is [NAME]"
    - "Tell me about [NAME]" 
    - "Details of [NAME]"
    - "What is the [FIELD] of [NAME]"
    - "[NAME] information"
    """
    question_lower = user_question.lower()
    
    # Define common patterns that indicate a specific entity query
    patterns = [
        # Direct patterns
        r"who is\s+(.+?)(?:\?|$)",
        r"tell me about\s+(.+?)(?:\?|$)",
        r"details of\s+(.+?)(?:\?|$)",
        r"information about\s+(.+?)(?:\?|$)",
        r"show me\s+(.+?)(?:\?|$)",
        
        # Field-specific patterns
        r"what is the .+? of\s+(.+?)(?:\?|$)",
        r"(?:faculty|employee|student)?\s*id of\s+(.+?)(?:\?|$)",
        r"(?:roll|enrollment)\s*number of\s+(.+?)(?:\?|$)",
        r"department of\s+(.+?)(?:\?|$)",
        r"email of\s+(.+?)(?:\?|$)",
        
        # Event/activity patterns
        r"event\s+(.+?)(?:\?|$)",
        r"activity\s+(.+?)(?:\?|$)",
        r"competition\s+(.+?)(?:\?|$)",
        r"hackathon\s+(.+?)(?:\?|$)",
    ]
    
    # Try each pattern
    for pattern in patterns:
        match = re.search(pattern, question_lower)
        if match:
            entity_name = match.group(1).strip()
            # Clean up the extracted name
            entity_name = entity_name.rstrip('?.,!').strip()
            
            # Skip if it's too short or looks like a generic term
            if len(entity_name) > 1 and not entity_name in ['it', 'that', 'this', 'them', 'him', 'her']:
                # Clean up common suffixes that might indicate context rather than part of the name
                # Handle patterns like "John Doe from AIML" -> extract just "John Doe"
                for suffix_pattern in [r'\s+from\s+\w+$', r'\s+in\s+\w+$', r'\s+at\s+\w+$', r'\s+department$']:
                    entity_name = re.sub(suffix_pattern, '', entity_name, flags=re.IGNORECASE)
                
                # Restore original capitalization from the original question
                original_start = user_question.lower().find(entity_name.lower())
                if original_start != -1:
                    entity_name = user_question[original_start:original_start + len(entity_name)]
                
                print(f"Generic fallback: Extracted '{entity_name}' from pattern '{pattern}' for API {api_path}")
                return {"type": "specific_entity_details", "value": entity_name}
    
    return None

class AskBipDataRequest(BaseModel):
    user_question: str
    target_bip_api_path: Optional[str] = None 
    item_id: Optional[Any] = None 

def parse_nova_api_response_data(api_response_json: Dict[str, Any], resource_name_hint: str = "") -> List[Dict[str, Any]]:
    if not isinstance(api_response_json, dict):
        print(f"Error: API response for {resource_name_hint} is not a dictionary. Type: {type(api_response_json)}")
        raise ValueError(f"Invalid API response format for {resource_name_hint}: Expected a dictionary.")

    raw_resource_items = api_response_json.get('resources')

    if not isinstance(raw_resource_items, list):
        available_keys = list(api_response_json.keys())
        print(f"Info: 'resources' key not found or not a list in API response for {resource_name_hint}. Available keys: {available_keys}. Trying 'data' key.")
        if 'data' in api_response_json and isinstance(api_response_json['data'], list):
            raw_resource_items = api_response_json['data']
        elif 'data' in api_response_json and isinstance(api_response_json['data'], dict): 
            print(f"Info: 'data' key is a dictionary for {resource_name_hint}. Wrapping in a list.")
            raw_resource_items = [api_response_json['data']]
        else:
            print(f"Warning: Could not find a list of resource items (expected under 'resources' or 'data') for {resource_name_hint}. Top-level keys: {available_keys}. Returning empty list.")
            return [] 
    
    if not raw_resource_items: 
        print(f"Info: No resource items found in 'resources' or 'data' list for {resource_name_hint}. Returning empty list.")
        return []

    parsed_items: List[Dict[str, Any]] = []
    for item_raw in raw_resource_items:
        if not isinstance(item_raw, dict):
            print(f"Warning: Skipping a raw resource item for {resource_name_hint} as it's not a dictionary: {item_raw}")
            continue
        entry: Dict[str, Any] = {}
        item_id_val = item_raw.get('id')
        
        if isinstance(item_id_val, dict) and 'value' in item_id_val:
            entry['id'] = item_id_val['value']
        elif item_id_val is not None: 
            entry['id'] = item_id_val

        attributes = item_raw.get('attributes')
        if isinstance(attributes, dict):
            for key, value in attributes.items():
                entry[key] = value
        
        fields_list = item_raw.get('fields') 
        if isinstance(fields_list, list): 
            for field_dict in fields_list:
                if isinstance(field_dict, dict) and 'attribute' in field_dict:
                    if field_dict['attribute'] not in entry:
                         entry[field_dict['attribute']] = field_dict.get('value')
        
        if 'id' not in entry and item_id_val is not None and not isinstance(item_id_val, dict):
             entry['id'] = item_id_val

        for key, value in item_raw.items():
            if key not in entry and key not in ['id', 'type', 'attributes', 'fields', 'relationships', 'links', 'meta']: 
                entry[key] = value
        
        if entry: 
            parsed_items.append(entry)
    return parsed_items

async def handle_faculty_for_my_courses_query(request: Request, user_question: str) -> Dict[str, Any]:
    print("--- Handling 'faculty_for_my_courses' query ---")
    student_details = await get_student_details_from_session(request) 

    if not student_details:
        return {"answer": "Sorry, I couldn't retrieve your student details to find your faculty.", "data_source": None}

    department_id = student_details.get('department_id') 
    department_name = student_details.get('department_name') 
    current_semester = student_details.get('current_semester') 

    if not department_id or not current_semester:
        return {"answer": "Hmm, I couldn't find your current department or semester details to look up faculty.", "data_source": "student_details_lookup"}

    print(f"--- Student context: Dept ID: {department_id}, Semester: {current_semester} ---")
    
    api_params_for_faculty = {
        "perPage": "150",
        "filters": base64.b64encode(json.dumps([{"DateTime:created_at":[None,None]}]).encode('utf-8')).decode('utf-8')
    }
        
    should_fetch_all_pages_for_faculty = True
    faculty_mappings_path = "/nova-api/academic-course-faculty-mappings"
    
    print(f"--- Fetching faculty mappings for Dept ID: {department_id}, Sem: {current_semester} from {faculty_mappings_path} ---")
    
    final_api_path = faculty_mappings_path
    query_string = urllib.parse.urlencode(api_params_for_faculty)
    if query_string:
        final_api_path += "?" + query_string

    try:
        raw_data = await fetch_bip_data(request, final_api_path, fetch_all_pages=should_fetch_all_pages_for_faculty)
        parsed_data = parse_nova_api_response_data(raw_data, resource_name_hint=faculty_mappings_path)
        
        filtered_for_student_context = []
        if parsed_data:
            for item in parsed_data:
                s_dept_ids = item.get('student_department_id') 
                s_semester = item.get('student_semester')
                
                try:
                    dept_id_int = int(department_id)
                except ValueError: dept_id_int = -1 

                match_dept = False
                if isinstance(s_dept_ids, list) and dept_id_int in s_dept_ids:
                    match_dept = True
                
                match_sem = False
                if s_semester is not None:
                    try:
                        if int(s_semester) == int(current_semester):
                             match_sem = True
                    except ValueError: pass

                if match_dept and match_sem:
                    filtered_for_student_context.append(item)
            
            if not filtered_for_student_context and parsed_data: 
                print(f"--- Python filter for dept/sem yielded no results from {len(parsed_data)} items. ---")
                context_for_llm = [] 
            else:
                context_for_llm = filtered_for_student_context
                print(f"--- Found {len(context_for_llm)} faculty mappings after Python filter. ---")
        else: 
            context_for_llm = []

        if not context_for_llm:
             return {"answer": f"I found the course faculty list, but couldn't see specific entries for your department ({department_name}) and semester ({current_semester}). Maybe check if your details are up to date?", "data_source": final_api_path}

        llm_answer = await get_answer_from_llm(context_data=context_for_llm, user_question=user_question, query_details={"type": "general_listing", "value": None})
        return {"answer": llm_answer, "data_source": final_api_path}

    except Exception as e:
        print(f"Error in handle_faculty_for_my_courses_query: {e}")
        return {"answer": "Sorry, I ran into a problem trying to find your faculty information.", "data_source": faculty_mappings_path}

async def handle_multi_entity_comparison_query(request: Request, user_question: str, query_details: Dict[str, Any]) -> Dict[str, Any]:
    print(f"--- Handling 'multi_entity_comparison' query for entities: {query_details.get('entities')} ---")
    entities_info = query_details.get("entities", []) # List of {"name": "X", "type": "Y"}
    if not entities_info or len(entities_info) < 1: # Allow even single entity if type is specified for future use, though comparison needs 2
        return {"answer": "Please specify at least one name or item for this type of query.", "data_source": None}

    entity_profiles = []
    data_sources = []
    
    entity_type_to_api_path = {
        "student": "/nova-api/students",
        "faculty": "/nova-api/faculties",
        # Add other types like "course": "/nova-api/academic-courses" if needed
    }

    for entity_spec in entities_info[:3]: # Process up to 3 entities
        entity_name = entity_spec.get("name")
        entity_type = entity_spec.get("type") # e.g., "student", "faculty", or None

        if not entity_name:
            continue

        api_path_template = None
        # Determine API path based on specified type
        if entity_type and entity_type in entity_type_to_api_path:
            api_path_template = entity_type_to_api_path[entity_type]
        else: 
            # Default to searching students if type is unknown, not specified, or not in our map
            api_path_template = "/nova-api/students"
            print(f"--- Entity type for '{entity_name}' is '{entity_type or 'not specified'}', defaulting to search in students API. ---")
        
        entity_api_path = f"{api_path_template}?search={urllib.parse.quote(entity_name)}"
        data_sources.append(entity_api_path)

        try:
            print(f"--- Fetching profile for entity: '{entity_name}' (type: {entity_type or 'defaulted to student'}) from {entity_api_path} ---")
            raw_data = await fetch_bip_data(request, entity_api_path, fetch_all_pages=False)
            parsed_data_list = parse_nova_api_response_data(raw_data, resource_name_hint=entity_api_path)
            
            if parsed_data_list:
                profile = parsed_data_list[0] 
                profile["_profile_for_"] = entity_name
                profile["_profile_type_"] = entity_type or ("student" if api_path_template == "/nova-api/students" else "unknown") # Store the type used for fetching
                entity_profiles.append(profile)
            else:
                print(f"--- No details found for '{entity_name}' in {entity_api_path} ---")
                entity_profiles.append({"_profile_for_": entity_name, "_profile_type_": entity_type or ("student" if api_path_template == "/nova-api/students" else "unknown"), "error": f"Could not find details for {entity_name}."})
        except Exception as e:
            print(f"Error fetching profile for {entity_name}: {e}")
            entity_profiles.append({"_profile_for_": entity_name, "_profile_type_": entity_type or ("student" if api_path_template == "/nova-api/students" else "unknown"), "error": f"Error fetching details for {entity_name}."})
    
    if not entity_profiles: # Should not happen if entities_info was not empty
        return {"answer": "Sorry, I couldn't retrieve details for any of the individuals mentioned.", "data_source": ", ".join(data_sources)}

    # If only one entity was processed and it resulted in an error, or all resulted in errors
    if len(entity_profiles) == 1 and entity_profiles[0].get("error"):
         return {"answer": entity_profiles[0]["error"], "data_source": ", ".join(data_sources)}
    if all(p.get("error") for p in entity_profiles) and entity_profiles:
         return {"answer": "Sorry, I encountered errors retrieving details for all individuals mentioned.", "data_source": ", ".join(data_sources)}


    llm_answer = await get_answer_from_llm(
        context_data=entity_profiles, 
        user_question=user_question, 
        query_details=query_details 
    )
    return {"answer": llm_answer, "data_source": ", ".join(data_sources)}


@router.get("/bip-resource-data") 
async def get_bip_resource_data(
    request: Request,
    target_bip_api_path: str = "/nova-api/academic-feedbacks" 
):
    accept_json_header = "application/json, text/plain, */*"
    api_path_for_fetch = target_bip_api_path
    should_fetch_all = False
    
    path_parts = urllib.parse.urlparse(target_bip_api_path)
    base_path = path_parts.path
    current_api_params = urllib.parse.parse_qs(path_parts.query)
    current_api_params_single_value = {k: v[0] for k, v in current_api_params.items() if v}

    if base_path in ["/nova-api/students", "/nova-api/academic-feedbacks", "/nova-api/departments", "/nova-api/student-activity-masters", "/nova-api/student-achievement-loggers", "/nova-api/academic-course-faculty-mappings", "/nova-api/periodical-statuses"]:
        if "perPage" not in current_api_params_single_value:
             current_api_params_single_value["perPage"] = "150" 
        should_fetch_all = True 
    
    if current_api_params_single_value:
        query_string = urllib.parse.urlencode(current_api_params_single_value)
        api_path_for_fetch = f"{base_path}?{query_string}"
    else:
        api_path_for_fetch = base_path
    print(f"Direct GET: Constructed path for fetch_bip_data: {api_path_for_fetch}, fetch_all_pages: {should_fetch_all}")

    try:
        api_response_json = await fetch_bip_data(
            request, 
            api_path_for_fetch, 
            accept_header=accept_json_header,
            fetch_all_pages=should_fetch_all 
        )
        if not api_response_json or not isinstance(api_response_json, dict): 
             print(f"Error: fetch_bip_data for {api_path_for_fetch} returned no JSON dictionary.")
             raise HTTPException(status_code=500, detail=f"Failed to fetch or parse JSON data from BIP API path: {api_path_for_fetch}")
        
        parsed_data = parse_nova_api_response_data(api_response_json, resource_name_hint=api_path_for_fetch)
        return parsed_data 
    except HTTPException as e: 
        raise e
    except ValueError as e: 
        print(f"ValueError during API data processing for {api_path_for_fetch}: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing BIP API data for {api_path_for_fetch}: {str(e)}")
    except Exception as e:
        print(f"Unexpected error in get_bip_resource_data for {api_path_for_fetch}: {type(e).__name__} - {e}")
        raise HTTPException(status_code=500, detail=f"An unexpected server error occurred while fetching/processing {api_path_for_fetch}: {str(e)}")

@router.post("/ask")
async def ask_bip_data_with_llm(ask_request: AskBipDataRequest, request: Request):
    user_question = ask_request.user_question
    item_id_filter = ask_request.item_id
    base_effective_path = ask_request.target_bip_api_path 

    print(f"--- Debug: Initial base_effective_path: {base_effective_path}")
    print(f"--- Debug: User question: {user_question}")

    api_params = {} 
    should_fetch_all_pages = False 
    query_details_for_llm: Optional[Dict[str, Any]] = None 

    normalized_user_question = user_question.lower()
    achievement_keywords = ["my achievement", "my participation", "my logged activit", "my paper presentation record"] 
    FUZZY_MATCH_THRESHOLD = 90 
    
    if not base_effective_path:
        temp_query_details = await extract_query_type_and_value(user_question)
        query_details_for_llm = temp_query_details 

        if temp_query_details:
            print(f"Query type extraction result: {temp_query_details}") 
            query_type = temp_query_details.get("type")

            if query_type == "user_context_dependent_query":
                print(f"Query identified as user_context_dependent: {temp_query_details}")
                if temp_query_details.get("sub_type") == "faculty_for_my_courses":
                    return await handle_faculty_for_my_courses_query(request, user_question)
                else: 
                    print(f"Unknown sub_type for user_context_dependent_query: {temp_query_details.get('sub_type')}. Proceeding with general path selection.")
            
            elif query_type == "multi_entity_comparison":
                print(f"Query identified as multi_entity_comparison: {temp_query_details}")
                return await handle_multi_entity_comparison_query(request, user_question, temp_query_details)
        
        if not base_effective_path: 
            forced_path_for_achievements = None
            for keyword in achievement_keywords:
                if fuzz.partial_ratio(keyword, normalized_user_question) >= FUZZY_MATCH_THRESHOLD:
                    forced_path_for_achievements = "/nova-api/student-achievement-loggers"
                    print(f"Fuzzy keyword match (ratio >= {FUZZY_MATCH_THRESHOLD}) for '{keyword}' in '{normalized_user_question}'. Forcing path to /nova-api/student-achievement-loggers.")
                    break
            
            if forced_path_for_achievements:
                base_effective_path = forced_path_for_achievements
            else:
                print(f"No achievement keywords matched fuzzily. Attempting to determine path from question: \"{user_question}\"")
                selected_path = await determine_api_path_from_query(user_question, BIP_API_ENDPOINTS)
                if not selected_path:
                    return {"answer": "Could not determine the relevant BIP API to answer your question. Please try rephrasing or specify a target area.", "data_source": None}
                base_effective_path = selected_path 
                print(f"LLM selected API path: {base_effective_path}")

        if not query_details_for_llm: 
            query_details_for_llm = await extract_query_type_and_value(user_question)
        print(f"Query details for parameterization: {query_details_for_llm}")
        
        # Generic fallback: extract entity names from common question patterns
        if not query_details_for_llm and base_effective_path:
            query_details_for_llm = extract_entity_from_common_patterns(user_question, base_effective_path)

        # Handle people-based APIs with smart name search
        if base_effective_path in ["/nova-api/students", "/nova-api/faculties"]:
            if query_details_for_llm: 
                q_type = query_details_for_llm.get("type") 
                q_value = query_details_for_llm.get("value")
                if q_type == "specific_entity_details" and q_value: 
                    # Use smart name search instead of simple search parameter
                    search_result = await smart_name_search(request, base_effective_path, q_value, query_details_for_llm)
                    if search_result["success"]:
                        context_for_llm = search_result["data"]
                        llm_answer = await get_answer_from_llm(context_for_llm, user_question, query_details_for_llm)
                        return {"answer": llm_answer, "data_source": search_result["data_source"]}
                    else:
                        return {"answer": search_result["message"], "data_source": search_result["data_source"]}
                elif base_effective_path == "/nova-api/students" and q_type == "list_by_category" and query_details_for_llm.get("category_type") == "department_name" and q_value:
                    # Keep existing department filtering logic for students
                    department_id = await get_department_id_by_name(request, q_value)
                    if department_id:
                        print(f"Found department ID: {department_id} for name: {q_value}")
                        student_dept_filter_list = [{"Text:name":""}, {"resource:student-statuses:student_statuses":""}, {"Text:enroll_no":""}, {"Text:roll_no":""}, {"Text:email":""}, {"Select:batch":""}, {"Select:degree_level":""}, {"resource:departments:department": department_id}, {"resource:branch-masters:branch_masters":""}]
                        filter_str_json = json.dumps(student_dept_filter_list)
                        api_params["filters"] = base64.b64encode(filter_str_json.encode('utf-8')).decode('utf-8')
                        api_params["perPage"] = "150" 
                        should_fetch_all_pages = True 
                        print(f"Using department filter with ID: {department_id}, perPage: 150.")
                    else:
                        print(f"Could not find ID for department: {q_value}. Fetching with perPage=150 for broader student results.")
                        api_params["perPage"] = "150"; should_fetch_all_pages = True
                else: 
                    print(f"General {base_effective_path} query. Fetching with perPage=150 and all pages.")
                    api_params["perPage"] = "150"; should_fetch_all_pages = True
            else:
                print(f"No query details for {base_effective_path}. Fetching with perPage=150 and all pages.")
                api_params["perPage"] = "150"; should_fetch_all_pages = True
        
        elif base_effective_path == "/nova-api/student-activity-masters":
            if query_details_for_llm and query_details_for_llm.get("type") == "specific_entity_details" and query_details_for_llm.get("value"):
                event_name = query_details_for_llm.get("value")
                empty_event_filters = [{"Text:event_code":""}, {"Text:event_name":""}, {"Text:organizer":""}, {"Text:web_url":""}, {"Select:status":""}, {"Date:start_date":[None,None]}, {"Date:end_date":[None,None]}, {"Text:location":""}, {"Text:competition_name":""}, {"Select:rewards_eligible":""}, {"Number:participation_rewards":[None,None]}, {"DateTime:created_at":[None,None]}, {"DateTime:updated_at":[None,None]}]
                api_params["filters"] = base64.b64encode(json.dumps(empty_event_filters).encode('utf-8')).decode('utf-8')
                api_params["search"] = event_name 
                should_fetch_all_pages = False 
                print(f"Using search parameter '{event_name}' with empty filters for specific event. Fetching single page (API default perPage).")
            elif query_details_for_llm and query_details_for_llm.get("type") == "list_by_category" and query_details_for_llm.get("category_type") in ["event_category", "location", "organizer"] and query_details_for_llm.get("value"):
                api_params["search"] = query_details_for_llm.get("value") 
                api_params["perPage"] = "150"; should_fetch_all_pages = True
                print(f"Searching student activities by {query_details_for_llm.get('category_type')} '{query_details_for_llm.get('value')}' using search param, with perPage=150.")
            elif query_details_for_llm and query_details_for_llm.get("type") == "general_listing" and query_details_for_llm.get("value"):
                api_params["search"] = query_details_for_llm.get("value")
                api_params["perPage"] = "150"; should_fetch_all_pages = True
                print(f"General search for student activities with keywords '{query_details_for_llm.get('value')}', perPage=150.")
            else: 
                api_params["perPage"] = "150"; should_fetch_all_pages = True
                print(f"Fetching all pages for {base_effective_path} (student activities) with perPage=150.")

        elif base_effective_path in ["/nova-api/faculties"]:
            # Generic handling for people/entity APIs
            if query_details_for_llm:
                q_type = query_details_for_llm.get("type")
                q_value = query_details_for_llm.get("value")
                if q_type == "specific_entity_details" and q_value:
                    api_params["search"] = q_value
                    should_fetch_all_pages = False
                    entity_type = base_effective_path.split("/")[-1].rstrip('s')  # "faculties" -> "faculty"
                    print(f"Using search term for {entity_type}: {q_value}. Fetching single page.")
                else:
                    print(f"General {base_effective_path} query. Fetching with perPage=150 and all pages.")
                    api_params["perPage"] = "150"; should_fetch_all_pages = True
            else:
                print(f"No query details for {base_effective_path}. Fetching with perPage=150 and all pages.")
                api_params["perPage"] = "150"; should_fetch_all_pages = True

        elif base_effective_path in ["/nova-api/academic-feedbacks", "/nova-api/departments", "/nova-api/student-achievement-loggers", "/nova-api/academic-course-faculty-mappings", "/nova-api/periodical-statuses", "/nova-api/student-project-implementation-details", "/nova-api/student-paper-presentation-reports", "/nova-api/student-project-competition-reports", "/nova-api/student-technical-competition-reports", "/nova-api/internship-reports", "/nova-api/student-online-courses"]:
            if query_details_for_llm and query_details_for_llm.get("type") == "general_listing" and query_details_for_llm.get("value"):
                api_params["search"] = query_details_for_llm.get("value")
                print(f"General search for {base_effective_path} with keywords '{query_details_for_llm.get('value')}'")

            api_params["perPage"] = "150"; should_fetch_all_pages = True
            
            default_filters_map = {
                "/nova-api/student-achievement-loggers": [{"DateTime:created_at":[None,None]}],
                "/nova-api/academic-course-faculty-mappings": [{"DateTime:created_at":[None,None]}],
                "/nova-api/periodical-statuses": [{"Select:periodical":""},{"Select:semester":""},{"Select:status":""}],
                "/nova-api/student-project-implementation-details": [{"resource:student-project-details:student_project_details":""},{"resource:academic-years:academic_years":""},{"Select:semester":""},{"Select:week":""},{"Textarea:work_carried_out":""},{"Select:project_guide_verification":""},{"Date:verified_date":[None,None]},{"Select:guide_comments":""},{"DateTime:created_at":[None,None]}],
                "/nova-api/student-paper-presentation-reports": [{"resource:student-achievement-loggers:student_achievement_loggers":""},{"Text:paper_title":""},{"Date:start_date":[None,None]},{"Date:end_date":[None,None]},{"Select:status":""},{"Text:original_proof_name":""},{"Text:attested_proof_name":""},{"Select:iqac_verification":""},{"DateTime:created_at":[None,None]}],
                "/nova-api/student-project-competition-reports": [{"resource:student-achievement-loggers:student_achievement_loggers":""},{"Text:project_title":""},{"Date:from_date":[None,None]},{"Date:to_date":[None,None]},{"Select:iqac_verification":""},{"DateTime:created_at":[None,None]}],
                "/nova-api/student-technical-competition-reports": [{"resource:student-achievement-loggers:student_achievement_loggers":""},{"Text:event_title":""},{"Select:participated_as":""},{"Date:from_date":[None,None]},{"Date:to_date":[None,None]},{"Select:sponsorship_types":""},{"Select:status":""},{"Text:winning_proof_name":""},{"Text:original_proof_name":""},{"Text:attested_proof_name":""},{"Select:iqac_verification":""},{"DateTime:created_at":[None,None]}],
                "/nova-api/internship-reports": [{"resource:internship-trackers:internship_trackers":""},{"Enum:year_of_study":""},{"resource:ssigs:ssigs":""},{"resource:special-labs:special_labs":""},{"Select:sector":""},{"Text:address_line_1":""},{"Text:address_line_2":""},{"Text:city":""},{"Text:state":""},{"Text:postal_code":""},{"Text:country":""},{"Text:industry_website":""},{"Text:industry_contact_details":""},{"Select:referred_by":""},{"Enum:stipend_amount":""},{"Select:is_aicte":""},{"Text:full_document_name":""},{"Text:original_proof_name":""},{"Text:attested_proof_name":""},{"Select:iqac_verification":""},{"DateTime:created_at":[None,None]}],
                "/nova-api/student-online-courses": [{"resource:students:students":""},{"Enum:year_of_study":""},{"resource:special-labs:special_labs":""},{"resource:online-courses:online_course":""},{"Select:course_type":""},{"Select:project_outcome":""},{"Text:other_course_name":""},{"Select:marks_available":""},{"Enum:course_exemption":""},{"Date:course_start_date":[None,None]},{"Date:course_end_date":[None,None]},{"Date:exam_date":[None,None]},{"Text:other_sponsorship_name":""},{"Text:original_proof_name":""},{"Text:attested_proof_name":""},{"Select:iqac_verification":""},{"DateTime:created_at":[None,None]}]
            }
            if base_effective_path in default_filters_map and "filters" not in api_params: 
                default_filters = default_filters_map[base_effective_path]
                filter_str_json = json.dumps(default_filters)
                api_params["filters"] = base64.b64encode(filter_str_json.encode('utf-8')).decode('utf-8')
                print(f"Added default empty filters for {base_effective_path}")
                
            print(f"Fetching all pages for {base_effective_path} with perPage=150.")
        else: 
            # Generic fallback for any other API endpoint
            if query_details_for_llm:
                q_type = query_details_for_llm.get("type")
                q_value = query_details_for_llm.get("value")
                if q_type == "specific_entity_details" and q_value:
                    api_params["search"] = q_value
                    should_fetch_all_pages = False
                    print(f"Using search term for {base_effective_path}: {q_value}. Fetching single page.")
                elif q_type == "general_listing" and q_value:
                    api_params["search"] = q_value
                    api_params["perPage"] = "150"
                    should_fetch_all_pages = True
                    print(f"General search for {base_effective_path} with keywords '{q_value}', perPage=150.")
                else:
                    should_fetch_all_pages = False
                    print(f"Basic query for {base_effective_path}. Single page fetch.")
            else:
                should_fetch_all_pages = False
                print(f"No query details for {base_effective_path}. Single page fetch.")
    
    elif not api_params: 
        if base_effective_path in ["/nova-api/students", "/nova-api/academic-feedbacks", "/nova-api/student-activity-masters", "/nova-api/departments", "/nova-api/student-achievement-loggers", "/nova-api/academic-course-faculty-mappings", "/nova-api/periodical-statuses", "/nova-api/student-project-implementation-details", "/nova-api/student-paper-presentation-reports", "/nova-api/student-project-competition-reports", "/nova-api/student-technical-competition-reports", "/nova-api/internship-reports", "/nova-api/student-online-courses"]:
            path_query = urllib.parse.urlparse(base_effective_path).query
            path_params = urllib.parse.parse_qs(path_query)
            if "search" not in path_params and "filters" not in path_params: 
                api_params["perPage"] = "150"; should_fetch_all_pages = True
                print(f"User provided {base_effective_path} path without search/filters, fetching with perPage=150 and all pages.")
                
                default_filters_map = {
                    "/nova-api/student-achievement-loggers": [{"DateTime:created_at":[None,None]}],
                    "/nova-api/academic-course-faculty-mappings": [{"DateTime:created_at":[None,None]}],
                    "/nova-api/periodical-statuses": [{"Select:periodical":""},{"Select:semester":""},{"Select:status":""}],
                    "/nova-api/student-project-implementation-details": [{"resource:student-project-details:student_project_details":""},{"resource:academic-years:academic_years":""},{"Select:semester":""},{"Select:week":""},{"Textarea:work_carried_out":""},{"Select:project_guide_verification":""},{"Date:verified_date":[None,None]},{"Select:guide_comments":""},{"DateTime:created_at":[None,None]}],
                    "/nova-api/student-paper-presentation-reports": [{"resource:student-achievement-loggers:student_achievement_loggers":""},{"Text:paper_title":""},{"Date:start_date":[None,None]},{"Date:end_date":[None,None]},{"Select:status":""},{"Text:original_proof_name":""},{"Text:attested_proof_name":""},{"Select:iqac_verification":""},{"DateTime:created_at":[None,None]}],
                    "/nova-api/student-project-competition-reports": [{"resource:student-achievement-loggers:student_achievement_loggers":""},{"Text:project_title":""},{"Date:from_date":[None,None]},{"Date:to_date":[None,None]},{"Select:iqac_verification":""},{"DateTime:created_at":[None,None]}],
                    "/nova-api/student-technical-competition-reports": [{"resource:student-achievement-loggers:student_achievement_loggers":""},{"Text:event_title":""},{"Select:participated_as":""},{"Date:from_date":[None,None]},{"Date:to_date":[None,None]},{"Select:sponsorship_types":""},{"Select:status":""},{"Text:winning_proof_name":""},{"Text:original_proof_name":""},{"Text:attested_proof_name":""},{"Select:iqac_verification":""},{"DateTime:created_at":[None,None]}],
                    "/nova-api/internship-reports": [{"resource:internship-trackers:internship_trackers":""},{"Enum:year_of_study":""},{"resource:ssigs:ssigs":""},{"resource:special-labs:special_labs":""},{"Select:sector":""},{"Text:address_line_1":""},{"Text:address_line_2":""},{"Text:city":""},{"Text:state":""},{"Text:postal_code":""},{"Text:country":""},{"Text:industry_website":""},{"Text:industry_contact_details":""},{"Select:referred_by":""},{"Enum:stipend_amount":""},{"Select:is_aicte":""},{"Text:full_document_name":""},{"Text:original_proof_name":""},{"Text:attested_proof_name":""},{"Select:iqac_verification":""},{"DateTime:created_at":[None,None]}],
                    "/nova-api/student-online-courses": [{"resource:students:students":""},{"Enum:year_of_study":""},{"resource:special-labs:special_labs":""},{"resource:online-courses:online_course":""},{"Select:course_type":""},{"Select:project_outcome":""},{"Text:other_course_name":""},{"Select:marks_available":""},{"Enum:course_exemption":""},{"Date:course_start_date":[None,None]},{"Date:course_end_date":[None,None]},{"Date:exam_date":[None,None]},{"Text:other_sponsorship_name":""},{"Text:original_proof_name":""},{"Text:attested_proof_name":""},{"Select:iqac_verification":""},{"DateTime:created_at":[None,None]}]
                }
                if base_effective_path in default_filters_map and "filters" not in path_params: 
                    default_filters = default_filters_map[base_effective_path]
                    current_filters_b64 = api_params.get("filters") 
                    if not current_filters_b64: 
                        filter_str_json = json.dumps(default_filters)
                        api_params["filters"] = base64.b64encode(filter_str_json.encode('utf-8')).decode('utf-8')
                        print(f"Added default empty filters for user-provided {base_effective_path}")
            else: 
                print(f"User provided {base_effective_path} with search/filters, fetching single page (API default perPage).")
                should_fetch_all_pages = False 
    
    final_api_path_with_params = base_effective_path
    if api_params:
        path_parts = urllib.parse.urlparse(base_effective_path)
        clean_base_path = path_parts.path
        existing_query_dict = urllib.parse.parse_qs(path_parts.query)
        for key, val_list in existing_query_dict.items():
            if val_list: existing_query_dict[key] = val_list[0]
        
        merged_params = {**existing_query_dict, **api_params} 
        query_string = urllib.parse.urlencode(merged_params)
        final_api_path_with_params = clean_base_path
        if query_string: final_api_path_with_params += "?" + query_string
            
    print(f"Final API path for fetch_bip_data: {final_api_path_with_params}")
            
    accept_json_header = "application/json, text/plain, */*"
    try:
        api_response_json = await fetch_bip_data(
            request,
            final_api_path_with_params, 
            accept_header=accept_json_header,
            fetch_all_pages=should_fetch_all_pages 
        )
        if not api_response_json or not isinstance(api_response_json, dict):
            print(f"Error or no data: fetch_bip_data for {final_api_path_with_params} returned non-dict or empty.")
            parsed_data = []
        else:
            parsed_data = parse_nova_api_response_data(api_response_json, resource_name_hint=final_api_path_with_params)

        context_for_llm = parsed_data
        if item_id_filter is not None and parsed_data: 
            try:
                filter_id_typed = int(item_id_filter) 
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid item_id format: '{item_id_filter}'. Must be convertible to an integer.")
            context_for_llm = [item for item in parsed_data if item.get('id') == filter_id_typed]
            if not context_for_llm:
                print(f"Info: Item with ID '{filter_id_typed}' not found in data from {final_api_path_with_params}.")
        
        if not context_for_llm and item_id_filter is not None: 
             return {"answer": f"No data found for item ID '{item_id_filter}' in the resource '{final_api_path_with_params}'.", "data_source": final_api_path_with_params} 
        
        if not context_for_llm and not parsed_data: 
             print(f"No data returned from API path {final_api_path_with_params} to send to LLM.")
             
             # Use universal smart name search for people-based APIs
             if api_params.get("search") and base_effective_path in ["/nova-api/students", "/nova-api/faculties"]:
                 search_term = api_params["search"]
                 search_result = await smart_name_search(request, base_effective_path, search_term, query_details_for_llm)
                 
                 if search_result["success"]:
                     llm_answer = await get_answer_from_llm(
                         context_data=search_result["data"],
                         user_question=user_question,
                         query_details=query_details_for_llm
                     )
                     return {"answer": llm_answer, "data_source": search_result["data_source"]}
                 else:
                     return {"answer": search_result["message"], "data_source": search_result["data_source"]}

        llm_answer = await get_answer_from_llm(
            context_data=context_for_llm, 
            user_question=user_question,
            query_details=query_details_for_llm 
        )
        return {"answer": llm_answer, "data_source": final_api_path_with_params} 
    except HTTPException as e:
        raise e
    except ValueError as e: 
        print(f"ValueError during data processing for {final_api_path_with_params} with question '{user_question}': {e}")
        raise HTTPException(status_code=500, detail=f"Error processing data for LLM: {str(e)}")
    except Exception as e:
        print(f"Unexpected error in ask_bip_data_with_llm for {final_api_path_with_params}: {type(e).__name__} - {e}")
        raise HTTPException(status_code=500, detail=f"An unexpected server error occurred with LLM interaction: {str(e)}")
    