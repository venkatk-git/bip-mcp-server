# packages/mcp-server/routes/assistant_routes.py
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse 
from pydantic import BaseModel
from ..core.bip_service import fetch_bip_data, get_department_id_by_name, get_student_details_from_session # Assuming this new helper
from ..core.llm_service import get_answer_from_llm, determine_api_path_from_query, extract_query_type_and_value 
from ..core.bip_api_registry import BIP_API_ENDPOINTS 

from typing import List, Dict, Any, Optional
import urllib.parse
import base64 
import json 

router = APIRouter()

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
        # Prioritize 'id' directly from item_raw if it exists at top level
        item_id_val = item_raw.get('id')
        
        # If 'id' is a dict (like in Nova responses), extract 'value'
        if isinstance(item_id_val, dict) and 'value' in item_id_val:
            entry['id'] = item_id_val['value']
        elif item_id_val is not None: # if id is already a simple value
            entry['id'] = item_id_val

        attributes = item_raw.get('attributes')
        if isinstance(attributes, dict):
            for key, value in attributes.items():
                entry[key] = value
        
        fields_list = item_raw.get('fields') 
        if isinstance(fields_list, list): 
            for field_dict in fields_list:
                if isinstance(field_dict, dict) and 'attribute' in field_dict:
                    # Prefer attributes if already set, otherwise take from fields
                    if field_dict['attribute'] not in entry:
                         entry[field_dict['attribute']] = field_dict.get('value')
        
        # Ensure top-level 'id' (if simple type) is preserved if not set from 'attributes' or 'fields'
        if 'id' not in entry and item_id_val is not None and not isinstance(item_id_val, dict):
             entry['id'] = item_id_val

        # Add other top-level keys not typically part of Nova's structure, if they exist
        for key, value in item_raw.items():
            if key not in entry and key not in ['id', 'type', 'attributes', 'fields', 'relationships', 'links', 'meta']: 
                entry[key] = value
        
        if entry: 
            parsed_items.append(entry)
    return parsed_items

async def handle_faculty_for_my_courses_query(request: Request, user_question: str) -> Dict[str, Any]:
    print("--- Handling 'faculty_for_my_courses' query ---")
    student_details = await get_student_details_from_session(request) # Needs to be implemented in bip_service

    if not student_details:
        return {"answer": "Sorry, I couldn't retrieve your student details to find your faculty.", "data_source": None}

    # Extract necessary details - these field names are assumptions and need verification
    # student_bip_id = student_details.get('id') # Assuming 'id' is the BIP internal ID
    department_id = student_details.get('department_id') # e.g., 31
    department_name = student_details.get('department_name') # e.g., "Artificial Intelligence and Machine Learning"
    current_semester = student_details.get('current_semester') # e.g., 4
    # current_academic_year_id = student_details.get('current_academic_year_id') # This might be tricky

    if not department_id or not current_semester:
        return {"answer": "Hmm, I couldn't find your current department or semester details to look up faculty.", "data_source": "student_details_lookup"}

    print(f"--- Student context: Dept ID: {department_id}, Semester: {current_semester} ---")

    # Construct filters for /nova-api/academic-course-faculty-mappings
    # The exact filter keys and structure need to match what the API expects.
    # This is based on the cURL's data structure where student_department_id is a list.
    # And assuming the API filters on these fields directly.
    
    # We need to find the 'id' for the department name if student_details only gives name
    # Or if student_details gives department_id directly, use that.
    # For now, assuming department_id is the numeric ID.
    
    # The cURL for academic-course-faculty-mappings had a generic created_at filter.
    # The actual data fields for filtering seem to be 'student_department_id' and 'student_semester'.
    # The 'student_department_id' in the API response was a list like [22].
    # The 'student_semester' was a number like 2.
    # The filter structure for Nova usually involves a list of dicts.
    
    # Let's try to build a filter that matches the observed data structure.
    # This is speculative and needs to be confirmed with how Nova filters are applied via URL params.
    # For now, we'll use a broad search and let the LLM sift, as specific filtering is complex.
    # A more robust solution would involve knowing the exact filter keys.

    api_params_for_faculty = {
        "perPage": "150",
        # "search": f"{department_name} semester {current_semester}", # General search
        # Default empty filter as seen in cURL, or more specific if known
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
        
        # Further filter parsed_data in Python if department_id and semester are not directly filterable by API query params
        # This is a fallback if API filtering is not precise enough.
        filtered_for_student_context = []
        if parsed_data:
            for item in parsed_data:
                # Check student_department_id: it's a list in the example, e.g. "value": [22]
                s_dept_ids = item.get('student_department_id') 
                s_semester = item.get('student_semester')
                
                # Ensure department_id is treated as int for comparison if s_dept_ids contains ints
                try:
                    dept_id_int = int(department_id)
                except ValueError:
                    dept_id_int = -1 # Should not happen if sourced correctly

                match_dept = False
                if isinstance(s_dept_ids, list) and dept_id_int in s_dept_ids:
                    match_dept = True
                
                match_sem = False
                if s_semester is not None:
                    try:
                        if int(s_semester) == int(current_semester):
                             match_sem = True
                    except ValueError: pass # s_semester might not be int-like

                if match_dept and match_sem:
                    filtered_for_student_context.append(item)
            
            if not filtered_for_student_context and parsed_data: # If initial fetch had data but python filter yielded none
                print(f"--- Python filter for dept/sem yielded no results from {len(parsed_data)} items. Using all for LLM. ---")
                # This might mean the student is not in any of the fetched mappings for that dept/sem,
                # or the dept/sem in the mapping data is not matching.
                # For safety, pass all parsed_data to LLM if python filter fails to narrow down.
                # context_for_llm = parsed_data # Or decide to return "no specific faculty found for your dept/sem"
                context_for_llm = [] # Prefer to say not found if Python filter fails
            else:
                context_for_llm = filtered_for_student_context
                print(f"--- Found {len(context_for_llm)} faculty mappings after Python filter. ---")

        else: # No data from API
            context_for_llm = []

        if not context_for_llm:
             return {"answer": f"I found the course faculty list, but couldn't see specific entries for your department ({department_name}) and semester ({current_semester}). Maybe check if your details are up to date?", "data_source": final_api_path}

        # Use the original user_question for the LLM to answer based on this specific context
        llm_answer = await get_answer_from_llm(context_data=context_for_llm, user_question=user_question, query_details={"type": "general_listing", "value": None}) # Treat as general listing for answering
        return {"answer": llm_answer, "data_source": final_api_path}

    except Exception as e:
        print(f"Error in handle_faculty_for_my_courses_query: {e}")
        return {"answer": "Sorry, I ran into a problem trying to find your faculty information.", "data_source": faculty_mappings_path}


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

    if base_path in ["/nova-api/students", "/nova-api/academic-feedbacks", "/nova-api/departments", "/nova-api/student-activity-masters", "/nova-api/student-achievement-loggers", "/nova-api/academic-course-faculty-mappings"]:
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
    
    if not base_effective_path:
        # First, check for user_context_dependent_query before keyword or LLM path selection
        temp_query_details = await extract_query_type_and_value(user_question)
        if temp_query_details and temp_query_details.get("type") == "user_context_dependent_query":
            query_details_for_llm = temp_query_details
            print(f"Query identified as user_context_dependent: {query_details_for_llm}")
            if temp_query_details.get("sub_type") == "faculty_for_my_courses":
                return await handle_faculty_for_my_courses_query(request, user_question)
            # Add other sub_type handlers here if needed
            else: # Unknown sub_type, fall through to general path selection
                print(f"Unknown sub_type for user_context_dependent_query: {temp_query_details.get('sub_type')}. Proceeding with general path selection.")
                pass # Fall through

        if not base_effective_path: # If not set by user_context_dependent logic
            forced_path_for_achievements = None
            for keyword in achievement_keywords:
                if keyword in normalized_user_question:
                    forced_path_for_achievements = "/nova-api/student-achievement-loggers"
                    print(f"Keyword '{keyword}' found. Forcing path to /nova-api/student-achievement-loggers.")
                    break
            
            if forced_path_for_achievements:
                base_effective_path = forced_path_for_achievements
            else:
                print(f"No achievement keywords found. Attempting to determine path from question: \"{user_question}\"")
                selected_path = await determine_api_path_from_query(user_question, BIP_API_ENDPOINTS)
                if not selected_path:
                    return {"answer": "Could not determine the relevant BIP API to answer your question. Please try rephrasing or specify a target area.", "data_source": None}
                base_effective_path = selected_path 
                print(f"LLM selected API path: {base_effective_path}")

        # Re-fetch query_details if not already fetched (e.g. if path was forced by keyword)
        if not query_details_for_llm:
            query_details_for_llm = await extract_query_type_and_value(user_question)
        print(f"Query type extraction result (used for parameterization): {query_details_for_llm}")


        if base_effective_path == "/nova-api/students":
            if query_details_for_llm: # Use the potentially updated query_details_for_llm
                query_type = query_details_for_llm.get("type")
                query_value = query_details_for_llm.get("value")

                if query_type == "specific_entity_details" and query_value: 
                    api_params["search"] = query_value
                    should_fetch_all_pages = False 
                    print(f"Using search term for student: {query_value}. Fetching single page.")
                elif query_type == "list_by_category" and query_details_for_llm.get("category_type") == "department_name" and query_value:
                    department_id = await get_department_id_by_name(request, query_value)
                    if department_id:
                        print(f"Found department ID: {department_id} for name: {query_value}")
                        student_dept_filter_list = [
                            {"Text:name":""}, {"resource:student-statuses:student_statuses":""},
                            {"Text:enroll_no":""}, {"Text:roll_no":""}, {"Text:email":""},
                            {"Select:batch":""}, {"Select:degree_level":""},
                            {"resource:departments:department": department_id}, 
                            {"resource:branch-masters:branch_masters":""}
                        ]
                        filter_str_json = json.dumps(student_dept_filter_list)
                        api_params["filters"] = base64.b64encode(filter_str_json.encode('utf-8')).decode('utf-8')
                        api_params["perPage"] = "150" 
                        should_fetch_all_pages = True 
                        print(f"Using department filter with ID: {department_id}, perPage: 150.")
                    else:
                        print(f"Could not find ID for department: {query_value}. Fetching with perPage=150 for broader student results.")
                        api_params["perPage"] = "150"
                        should_fetch_all_pages = True
                else: 
                    print("General student query or unhandled specific student query. Fetching with perPage=150 and all pages.")
                    api_params["perPage"] = "150"
                    should_fetch_all_pages = True
        
        elif base_effective_path == "/nova-api/student-activity-masters":
            if query_details_for_llm and query_details_for_llm.get("type") == "specific_entity_details" and query_details_for_llm.get("value"):
                event_name = query_details_for_llm.get("value")
                empty_event_filters = [
                    {"Text:event_code":""}, {"Text:event_name":""}, {"Text:organizer":""}, 
                    {"Text:web_url":""}, {"Select:status":""}, {"Date:start_date":[None,None]}, 
                    {"Date:end_date":[None,None]}, {"Text:location":""}, {"Text:competition_name":""}, 
                    {"Select:rewards_eligible":""}, {"Number:participation_rewards":[None,None]}, 
                    {"DateTime:created_at":[None,None]}, {"DateTime:updated_at":[None,None]}
                ]
                filter_str_json = json.dumps(empty_event_filters)
                api_params["filters"] = base64.b64encode(filter_str_json.encode('utf-8')).decode('utf-8')
                api_params["search"] = event_name 
                should_fetch_all_pages = False 
                print(f"Using search parameter '{event_name}' with empty filters for specific event. Fetching single page (API default perPage).")
            elif query_details_for_llm and query_details_for_llm.get("type") == "list_by_category" and \
                 query_details_for_llm.get("category_type") in ["event_category", "location", "organizer"] and \
                 query_details_for_llm.get("value"):
                api_params["search"] = query_details_for_llm.get("value") 
                api_params["perPage"] = "150" 
                should_fetch_all_pages = True
                print(f"Searching student activities by {query_details_for_llm.get('category_type')} '{query_details_for_llm.get('value')}' using search param, with perPage=150.")
            elif query_details_for_llm and query_details_for_llm.get("type") == "general_listing" and query_details_for_llm.get("value"):
                api_params["search"] = query_details_for_llm.get("value")
                api_params["perPage"] = "150"
                should_fetch_all_pages = True
                print(f"General search for student activities with keywords '{query_details_for_llm.get('value')}', perPage=150.")
            else: 
                api_params["perPage"] = "150" 
                should_fetch_all_pages = True
                print(f"Fetching all pages for {base_effective_path} (student activities) with perPage=150.")

        elif base_effective_path in ["/nova-api/academic-feedbacks", "/nova-api/departments", "/nova-api/student-achievement-loggers", "/nova-api/academic-course-faculty-mappings"]:
            if query_details_for_llm and query_details_for_llm.get("type") == "general_listing" and query_details_for_llm.get("value"):
                api_params["search"] = query_details_for_llm.get("value")
                print(f"General search for {base_effective_path} with keywords '{query_details_for_llm.get('value')}'")

            api_params["perPage"] = "150" 
            should_fetch_all_pages = True
            
            default_filters_map = {
                "/nova-api/student-achievement-loggers": [{"DateTime:created_at":[None,None]}],
                "/nova-api/academic-course-faculty-mappings": [{"DateTime:created_at":[None,None]}]
            }
            if base_effective_path in default_filters_map and "filters" not in api_params:
                default_filters = default_filters_map[base_effective_path]
                filter_str_json = json.dumps(default_filters)
                api_params["filters"] = base64.b64encode(filter_str_json.encode('utf-8')).decode('utf-8')
                print(f"Added default empty 'created_at' filter for {base_effective_path}")
                
            print(f"Fetching all pages for {base_effective_path} with perPage=150.")
        else: 
            should_fetch_all_pages = False
            print(f"Defaulting to single page fetch for {base_effective_path}")
    
    elif not api_params: 
        if base_effective_path in ["/nova-api/students", "/nova-api/academic-feedbacks", "/nova-api/student-activity-masters", "/nova-api/departments", "/nova-api/student-achievement-loggers", "/nova-api/academic-course-faculty-mappings"]:
            path_query = urllib.parse.urlparse(base_effective_path).query
            path_params = urllib.parse.parse_qs(path_query)
            if "search" not in path_params and "filters" not in path_params: 
                api_params["perPage"] = "150"
                should_fetch_all_pages = True
                print(f"User provided {base_effective_path} path without search/filters, fetching with perPage=150 and all pages.")
                
                default_filters_map = {
                    "/nova-api/student-achievement-loggers": [{"DateTime:created_at":[None,None]}],
                    "/nova-api/academic-course-faculty-mappings": [{"DateTime:created_at":[None,None]}]
                }
                if base_effective_path in default_filters_map and "filters" not in api_params:
                    default_filters = default_filters_map[base_effective_path]
                    filter_str_json = json.dumps(default_filters)
                    api_params["filters"] = base64.b64encode(filter_str_json.encode('utf-8')).decode('utf-8')
                    print(f"Added default empty 'created_at' filter for user-provided {base_effective_path}")
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
