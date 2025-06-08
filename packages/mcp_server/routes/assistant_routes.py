# packages/mcp-server/routes/assistant_routes.py
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse 
from pydantic import BaseModel
from ..core.bip_service import fetch_bip_data, get_department_id_by_name 
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
        raise ValueError(f"Invalid API response format for {resource_name_hint}: Expected a dictionary.")

    raw_resource_items = api_response_json.get('resources')

    if not isinstance(raw_resource_items, list):
        available_keys = list(api_response_json.keys())
        if 'data' in api_response_json and isinstance(api_response_json['data'], list):
            raw_resource_items = api_response_json['data']
        elif 'data' in api_response_json and isinstance(api_response_json['data'], dict): 
            raw_resource_items = [api_response_json['data']]
        else:
            return [] 
    
    if not raw_resource_items: 
        return []

    parsed_items: List[Dict[str, Any]] = []
    for item_raw in raw_resource_items:
        if not isinstance(item_raw, dict):
            continue
        entry: Dict[str, Any] = {}
        item_id_val = item_raw.get('id')
        if item_id_val is not None: 
             entry['id'] = item_id_val
        
        attributes = item_raw.get('attributes')
        if isinstance(attributes, dict):
            for key, value in attributes.items():
                entry[key] = value
        
        fields_list = item_raw.get('fields') 
        if isinstance(fields_list, list) and not attributes: 
            for field_dict in fields_list:
                if isinstance(field_dict, dict) and 'attribute' in field_dict:
                    entry[field_dict['attribute']] = field_dict.get('value')
        elif isinstance(fields_list, list): 
             for field_dict in fields_list:
                if isinstance(field_dict, dict) and 'attribute' in field_dict:
                    if field_dict['attribute'] not in entry:
                         entry[field_dict['attribute']] = field_dict.get('value')

        if 'id' not in entry and item_id_val is not None: 
             entry['id'] = item_id_val

        for key, value in item_raw.items():
            if key not in entry and key not in ['id', 'type', 'attributes', 'fields', 'relationships', 'links', 'meta']: 
                entry[key] = value
        
        if entry: 
            parsed_items.append(entry)
    return parsed_items

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

    if base_path in ["/nova-api/students", "/nova-api/academic-feedbacks", "/nova-api/departments", "/nova-api/student-activity-masters"]:
        if "perPage" not in current_api_params_single_value:
             current_api_params_single_value["perPage"] = "150" 
        should_fetch_all = True 
    
    if current_api_params_single_value:
        query_string = urllib.parse.urlencode(current_api_params_single_value)
        api_path_for_fetch = f"{base_path}?{query_string}"
    else:
        api_path_for_fetch = base_path

    try:
        api_response_json = await fetch_bip_data(
            request, 
            api_path_for_fetch, 
            accept_header=accept_json_header,
            fetch_all_pages=should_fetch_all 
        )
        if not api_response_json or not isinstance(api_response_json, dict): 
             raise HTTPException(status_code=500, detail=f"Failed to fetch or parse JSON data from BIP API path: {api_path_for_fetch}")
        
        parsed_data = parse_nova_api_response_data(api_response_json, resource_name_hint=api_path_for_fetch)
        return parsed_data 
    except HTTPException as e: 
        raise e
    except ValueError as e: 
        raise HTTPException(status_code=500, detail=f"Error processing BIP API data for {api_path_for_fetch}: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected server error occurred while fetching/processing {api_path_for_fetch}: {str(e)}")

@router.post("/ask")
async def ask_bip_data_with_llm(ask_request: AskBipDataRequest, request: Request):
    user_question = ask_request.user_question
    item_id_filter = ask_request.item_id
    base_effective_path = ask_request.target_bip_api_path 
    api_params = {} 
    should_fetch_all_pages = False 
    query_details_for_llm: Optional[Dict[str, Any]] = None 

    if not base_effective_path:
        selected_path = await determine_api_path_from_query(user_question, BIP_API_ENDPOINTS)
        if not selected_path:
            return {"answer": "Could not determine the relevant BIP API to answer your question. Please try rephrasing or specify a target area.", "data_source": None}
        base_effective_path = selected_path 

        query_details = await extract_query_type_and_value(user_question) 
        query_details_for_llm = query_details 

        if base_effective_path == "/nova-api/students":
            if query_details:
                query_type = query_details.get("type")
                query_value = query_details.get("value")

                if query_type == "specific_entity_details" and query_value: 
                    api_params["search"] = query_value
                    should_fetch_all_pages = False 
                elif query_type == "list_by_category" and query_details.get("category_type") == "department_name" and query_value:
                    department_id = await get_department_id_by_name(request, query_value)
                    if department_id:
                        default_filters_template = [
                            {"Text:name":""}, {"resource:student-statuses:student_statuses":""},
                            {"Text:enroll_no":""}, {"Text:roll_no":""}, {"Text:email":""},
                            {"Select:batch":""}, {"Select:degree_level":""},
                            {"resource:branch-masters:branch_masters":""}
                        ]
                        final_filter_list = []
                        has_dept_filter = False
                        for f_item_template in default_filters_template: # Iterate over a copy or new list
                            key = list(f_item_template.keys())[0]
                            # Create new dicts for final_filter_list to avoid modifying template
                            if key == "resource:departments:department": # This key is not in student filter template
                                final_filter_list.append({"resource:departments:department": department_id})
                                has_dept_filter = True
                            else:
                                final_filter_list.append(dict(f_item_template)) # Add a copy
                        if not has_dept_filter: # Add if not already (e.g. if template was different)
                             final_filter_list.append({"resource:departments:department": department_id})
                        
                        filter_str_json = json.dumps(final_filter_list)
                        api_params["filters"] = base64.b64encode(filter_str_json.encode('utf-8')).decode('utf-8')
                        api_params["perPage"] = "150" 
                        should_fetch_all_pages = True 
                    else:
                        api_params["perPage"] = "150"
                        should_fetch_all_pages = True
                else: 
                    api_params["perPage"] = "150"
                    should_fetch_all_pages = True
        
        elif base_effective_path == "/nova-api/student-activity-masters":
            if query_details and query_details.get("type") == "specific_entity_details" and query_details.get("value"):
                event_name = query_details.get("value")
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
            elif query_details and query_details.get("type") == "list_by_category" and \
                 query_details.get("category_type") in ["event_category", "location", "organizer"] and \
                 query_details.get("value"):
                api_params["search"] = query_details.get("value") 
                api_params["perPage"] = "150" 
                should_fetch_all_pages = True
            else: 
                api_params["perPage"] = "150" 
                should_fetch_all_pages = True

        elif base_effective_path in ["/nova-api/academic-feedbacks", "/nova-api/departments"]:
            api_params["perPage"] = "150" 
            should_fetch_all_pages = True
        else: 
            should_fetch_all_pages = False
    
    elif not api_params: 
        if base_effective_path in ["/nova-api/students", "/nova-api/academic-feedbacks", "/nova-api/student-activity-masters", "/nova-api/departments"]:
            path_query = urllib.parse.urlparse(base_effective_path).query
            path_params = urllib.parse.parse_qs(path_query)
            if "search" not in path_params and "filters" not in path_params:
                api_params["perPage"] = "150"
                should_fetch_all_pages = True
            else:
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
            
    accept_json_header = "application/json, text/plain, */*"
    try:
        api_response_json = await fetch_bip_data(
            request,
            final_api_path_with_params, 
            accept_header=accept_json_header,
            fetch_all_pages=should_fetch_all_pages 
        )
        if not api_response_json or not isinstance(api_response_json, dict):
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
        
        if not context_for_llm and item_id_filter is not None: 
             return {"answer": f"No data found for item ID '{item_id_filter}' in the resource '{final_api_path_with_params}'.", "data_source": final_api_path_with_params} 
        
        # if not context_for_llm and not parsed_data: # This print is redundant if context_for_llm is empty

        llm_answer = await get_answer_from_llm(
            context_data=context_for_llm, 
            user_question=user_question,
            query_details=query_details_for_llm 
        )
        return {"answer": llm_answer, "data_source": final_api_path_with_params} 
    except HTTPException as e:
        raise e
    except ValueError as e: 
        raise HTTPException(status_code=500, detail=f"Error processing data for LLM: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected server error occurred with LLM interaction: {str(e)}")
