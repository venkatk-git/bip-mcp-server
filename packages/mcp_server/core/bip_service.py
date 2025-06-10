# packages/mcp-server/core/bip_service.py
import httpx
from fastapi import Request, HTTPException
from typing import Any, List, Dict, Optional 
import json 
import time 
import urllib.parse # For parsing next_page_url

BIP_BASE_URL = "https://bip.bitsathy.ac.in"

_department_cache: Optional[List[Dict[str, Any]]] = None
_department_cache_expiry_seconds: int = 3600 
_department_cache_last_updated: float = 0.0

async def _fetch_and_cache_departments(request: Request) -> List[Dict[str, Any]]:
    global _department_cache, _department_cache_last_updated
    current_time = time.time()

    if _department_cache and (current_time - _department_cache_last_updated < _department_cache_expiry_seconds):
        return _department_cache

    try:
        # Department list is usually not excessively long, fetch_all_pages=True by default if it were paginated.
        # For now, assume it returns all in one go or default pagination is fine.
        department_api_data = await fetch_bip_data(request, "/nova-api/departments", accept_header="application/json", fetch_all_pages=True) 
        
        if not isinstance(department_api_data, dict) or "resources" not in department_api_data:
            return _department_cache if _department_cache else []

        parsed_departments: List[Dict[str, Any]] = []
        for dept_resource in department_api_data.get("resources", []):
            if not isinstance(dept_resource, dict):
                continue
            
            dept_id_obj = dept_resource.get("id")
            dept_id = None
            if isinstance(dept_id_obj, dict) and "value" in dept_id_obj: 
                dept_id = dept_id_obj["value"]
            elif isinstance(dept_id_obj, (int, str)): 
                dept_id = dept_id_obj

            dept_name = None
            fields = dept_resource.get("fields", [])
            for field in fields:
                if isinstance(field, dict) and field.get("attribute") == "name" and "value" in field:
                    dept_name = field["value"]
                    break 
            if not dept_name and "title" in dept_resource:
                 dept_name = dept_resource.get("title")

            if dept_id is not None and dept_name is not None:
                parsed_departments.append({"id": dept_id, "name": str(dept_name)})
        
        if not parsed_departments:
            return _department_cache if _department_cache else []

        _department_cache = parsed_departments
        _department_cache_last_updated = current_time
        return _department_cache
    except HTTPException as e:
        if _department_cache: return _department_cache
        raise
    except Exception as e:
        if _department_cache: return _department_cache
        return []

async def get_department_id_by_name(request: Request, department_name: str) -> Optional[int]:
    if not department_name: return None
    departments = await _fetch_and_cache_departments(request)
    if not departments: return None
    search_name_lower = department_name.lower().strip()
    for dept in departments:
        if dept.get("name", "").lower().strip() == search_name_lower:
            return int(dept["id"]) 
    return None

async def get_student_details_from_session(request: Request) -> Optional[Dict[str, Any]]:
    """
    Fetches the logged-in student's details (like department_id, department_name, current_semester)
    using information from the BIP session.
    """
    bip_session_data = request.session.get('bip_session_data')
    if not bip_session_data:
        print("Error in get_student_details_from_session: BIP session data not found.")
        return None

    user_bip_id_str = bip_session_data.get("wiki_user_id_cookie")
    user_bip_name = bip_session_data.get("wiki_user_name_cookie")

    student_api_path = None
    
    # Try to use user_bip_id_str as a numeric ID first
    numeric_user_id = None
    if user_bip_id_str:
        try:
            numeric_user_id = int(user_bip_id_str) # Check if it's a number
        except ValueError:
            # If user_bip_id_str is not a number, it might be the username/email.
            # In this case, we might prefer user_bip_name if it also exists and is different,
            # or just use user_bip_id_str as the search term if user_bip_name is absent.
            if not user_bip_name: # If user_bip_name is missing, use user_bip_id_str for search
                 user_bip_name = user_bip_id_str
            numeric_user_id = None # Ensure it's None so we fall to search by name

    if numeric_user_id is not None:
        student_api_path = f"/nova-api/students/{numeric_user_id}"
        print(f"--- Attempting to fetch student details by NUMERIC ID: {numeric_user_id} from {student_api_path} ---")
    elif user_bip_name: # Fallback to searching by name (which could be from user_bip_name or user_bip_id_str if it wasn't numeric)
        # Clean the name if it was URL encoded from the cookie (e.g. email)
        # However, wiki_user_name_cookie is usually not URL encoded itself.
        # The value from session should be the raw cookie value.
        search_term = user_bip_name
        if '%' in search_term: # Simple check if it might be URL encoded
            try:
                search_term = urllib.parse.unquote(search_term)
            except Exception:
                pass # Use as is if unquoting fails
        
        encoded_search_term = urllib.parse.quote(search_term)
        student_api_path = f"/nova-api/students?search={encoded_search_term}"
        print(f"--- Attempting to fetch student details by SEARCH TERM: '{search_term}' from {student_api_path} ---")
    else:
        print("Error in get_student_details_from_session: No user ID or name in BIP session for student lookup.")
        return None

    try:
        # Fetching a single student record, so fetch_all_pages=False (default) is fine.
        student_raw_data = await fetch_bip_data(request, student_api_path, accept_header="application/json")
        
        # The student API when fetching by ID might return the resource directly, not in a 'resources' list.
        # Or if by search, it will be in 'resources'. We need to handle both.
        
        student_resource = None
        if isinstance(student_raw_data, dict):
            if "resources" in student_raw_data and isinstance(student_raw_data["resources"], list) and student_raw_data["resources"]:
                student_resource = student_raw_data["resources"][0] # Take the first if search returned multiple
            elif "data" in student_raw_data and isinstance(student_raw_data["data"], dict): # Direct ID lookup often has 'data' as the resource
                student_resource = student_raw_data["data"]
            elif "id" in student_raw_data: # Sometimes the root object is the resource itself
                 student_resource = student_raw_data


        if not student_resource or not isinstance(student_resource, dict):
            print(f"Error in get_student_details_from_session: Could not find student resource in response from {student_api_path}. Response: {str(student_raw_data)[:200]}")
            return None

        # Now parse the student_resource. Field names are assumptions.
        # We need to inspect an actual student API response to get these right.
        # Example: student_resource might look like:
        # { "id": {"value": 123}, "fields": [ {"attribute": "name", "value": "Test Student"}, ... ] }
        # Or attributes: { "name": "Test Student", "department_id": 31, "current_semester": 4 }
        
        details = {}
        
        # Extract ID
        s_id_obj = student_resource.get("id")
        if isinstance(s_id_obj, dict) and "value" in s_id_obj:
            details["id"] = s_id_obj["value"]
        elif s_id_obj is not None:
            details["id"] = s_id_obj

        fields_list = student_resource.get("fields", [])
        if not isinstance(fields_list, list): # Should always be a list based on example
            print(f"Warning: 'fields' is not a list in student resource for user '{user_bip_id_str or user_bip_name}'.")
            fields_list = []

        department_name_from_field = None
        department_id_from_field = None
        semester_from_field = None

        for field in fields_list:
            if not isinstance(field, dict): continue
            attribute = field.get("attribute")
            if attribute == "department":
                department_name_from_field = field.get("value")
                # The 'department' field also has 'belongsToId' which is the department_id
                if field.get("belongsToRelationship") == "department": # Ensure it's the correct relationship
                    department_id_from_field = field.get("belongsToId")
            elif attribute == "semester":
                semester_from_field = field.get("value")
        
        details["department_name"] = department_name_from_field
        details["department_id"] = department_id_from_field
        details["current_semester"] = semester_from_field
        
        # Validate essential fields
        if details.get("department_id") is None or details.get("current_semester") is None:
            # department_name is good to have but department_id is crucial for filtering if available
            print(f"Warning: Missing department_id or current_semester in student details for user '{user_bip_id_str or user_bip_name}'. Details found: {details}")
            # Return None if critical info is missing, as the calling function relies on these.
            # Or return partial, and let caller handle. For now, let's be strict.
            if details.get("department_id") is None: # Department ID is more critical for precise filtering
                 print("Critical detail department_id missing.")
                 return None
            # If only semester is missing, maybe it can be defaulted or handled by LLM, but for now, require it.
            if details.get("current_semester") is None:
                 print("Critical detail current_semester missing.")
                 return None
        
        print(f"--- Successfully fetched and parsed student details: {details} ---")
        return details

    except HTTPException as e:
        print(f"HTTPException in get_student_details_from_session for {student_api_path}: {e.detail}")
        return None
    except Exception as e:
        print(f"Unexpected error in get_student_details_from_session for {student_api_path}: {e}")
        return None


async def fetch_bip_data(
    request: Request, 
    target_path_with_params: str, # Renamed to reflect it might have params
    accept_header: str = 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    fetch_all_pages: bool = False
) -> Any:
    bip_session_data = request.session.get('bip_session_data')
    if not bip_session_data:
        raise HTTPException(status_code=401, detail="BIP session data not found. Please use extension to sync.")

    cookies_dict = {
        "bip_session": bip_session_data.get("bip_session_cookie"),
        "XSRF-TOKEN": bip_session_data.get("xsrf_token_cookie"),
    }
    if bip_session_data.get("wiki_user_name_cookie"):
        cookies_dict["wiki_wiki_UserName"] = bip_session_data.get("wiki_user_name_cookie")
    if bip_session_data.get("wiki_user_id_cookie"):
        cookies_dict["wiki_wiki_UserID"] = bip_session_data.get("wiki_user_id_cookie")
    if bip_session_data.get("app_forward_auth_cookie"): # Check for the new cookie
        cookies_dict["app_forward_auth"] = bip_session_data.get("app_forward_auth_cookie")
    
    if not cookies_dict.get("bip_session") or not cookies_dict.get("XSRF-TOKEN"): # Keep existing check for essential cookies
         raise HTTPException(status_code=400, detail="Essential BIP cookies (bip_session, XSRF-TOKEN) missing from stored session data.")

    cookie_parts = []
    # Order might matter for some servers, typically less critical ones last or as received.
    # For now, just append.
    if cookies_dict.get("wiki_wiki_UserName"): cookie_parts.append(f"wiki_wiki_UserName={cookies_dict['wiki_wiki_UserName']}")
    if cookies_dict.get("wiki_wiki_UserID"): cookie_parts.append(f"wiki_wiki_UserID={cookies_dict['wiki_wiki_UserID']}")
    if cookies_dict.get("app_forward_auth"): cookie_parts.append(f"app_forward_auth={cookies_dict['app_forward_auth']}") # Add new cookie
    cookie_parts.append(f"XSRF-TOKEN={cookies_dict['XSRF-TOKEN']}") # Standard cookies
    cookie_parts.append(f"bip_session={cookies_dict['bip_session']}")
    cookie_header_value = "; ".join(cookie_parts)

    base_headers = {
        'accept': accept_header, 'accept-language': 'en-US,en;q=0.9', 'priority': 'u=1, i', 
        'referer': BIP_BASE_URL + '/', 'sec-ch-ua': '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"', 
        'sec-ch-ua-mobile': '?0', 'sec-ch-ua-platform': '"macOS"', 
        'sec-fetch-dest': 'empty' if "application/json" in accept_header.lower() else 'document',
        'sec-fetch-mode': 'cors' if "application/json" in accept_header.lower() else 'navigate',
        'sec-fetch-site': 'same-origin',
        'sec-fetch-user': '?1' if "text/html" in accept_header.lower() else None, 
        'upgrade-insecure-requests': '1' if "text/html" in accept_header.lower() else None, 
        'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36',
        'Cookie': cookie_header_value
    }
    current_headers = {k: v for k, v in base_headers.items() if v is not None}
    if "application/json" in accept_header.lower():
        current_headers['X-XSRF-TOKEN'] = bip_session_data.get("xsrf_token_cookie")
        current_headers['x-requested-with'] = 'XMLHttpRequest' 

    current_target_path = target_path_with_params
    
    async with httpx.AsyncClient() as client:
        all_resources_aggregated = []
        first_response_json = None
        page_count = 0
        max_pages_to_fetch = 5 # Adjusted safety limit (e.g., 5 * 150 = 750 records max)

        while current_target_path and page_count < max_pages_to_fetch:
            page_count += 1
            target_url = BIP_BASE_URL + current_target_path if not current_target_path.startswith("http") else current_target_path

            try:
                response = await client.get(target_url, headers=current_headers, follow_redirects=True, timeout=60.0)
                if "logout" in str(response.url).lower() or "login" in str(response.url).lower() or "sign-in" in str(response.url).lower():
                    if response.url.host == httpx.URL(BIP_BASE_URL).host and target_path_with_params not in str(response.url): # Check original path
                        raise HTTPException(status_code=401, detail="BIP session invalid or expired. Please re-sync with extension.")
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").lower()

                if "application/json" in content_type:
                    json_page_response = response.json()
                    if not first_response_json:
                        first_response_json = json_page_response # Store the first page structure

                    page_data = json_page_response.get("resources", []) if isinstance(json_page_response.get("resources"), list) else []
                    if not page_data and isinstance(json_page_response.get("data"), list):
                        page_data = json_page_response.get("data", [])
                    
                    all_resources_aggregated.extend(page_data)

                    if fetch_all_pages:
                        next_page_url_from_api = json_page_response.get("next_page_url")
                        if next_page_url_from_api:
                            # Nova often returns full URLs, extract path and query
                            parsed_next_url = urllib.parse.urlparse(next_page_url_from_api)
                            next_page_base_path = parsed_next_url.path
                            next_page_query_params = urllib.parse.parse_qs(parsed_next_url.query)

                            # Check if original target_path_with_params had a perPage, if so, try to maintain it
                            # This assumes the 'perPage' key is consistent.
                            initial_url_parts = urllib.parse.urlparse(target_path_with_params)
                            initial_query_params = urllib.parse.parse_qs(initial_url_parts.query)
                            desired_per_page = initial_query_params.get('perPage', [None])[0]

                            if desired_per_page:
                                # Override or add perPage in next_page_query_params
                                next_page_query_params['perPage'] = [desired_per_page]
                            
                            # Reconstruct current_target_path
                            current_target_path = next_page_base_path
                            if next_page_query_params:
                                current_target_path += "?" + urllib.parse.urlencode(next_page_query_params, doseq=True)
                            
                        else:
                            current_target_path = None # No more pages
                    else:
                        current_target_path = None # Only fetch one page if fetch_all_pages is False
                else: # Not JSON
                    if page_count == 1: # Only return non-JSON if it's the first (and only) page expected
                        return response.text
                    else: # Should not happen if first page was JSON and paginating
                        current_target_path = None # Stop pagination
            
            except httpx.HTTPStatusError as e:
                if e.response.status_code in [401, 419, 403]:
                    raise HTTPException(status_code=e.response.status_code, detail=f"BIP session/authorization error ({e.response.status_code}). Detail: {e.response.text[:100]}")
                raise HTTPException(status_code=e.response.status_code, detail=f"Error fetching from BIP: {e.response.status_code}. Response: {e.response.text[:200]}")
            except httpx.RequestError as e:
                raise HTTPException(status_code=503, detail=f"Network error communicating with BIP: {str(e)}")
            except json.JSONDecodeError as e:
                # Consider logging response.text[:200] if error persists in a real logger
                raise HTTPException(status_code=500, detail=f"Failed to decode JSON response from BIP API: {str(e)}")
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"An unexpected error occurred during data fetching: {str(e)}")

            if not fetch_all_pages: # Ensure we break after first page if not fetching all
                break
        
        # After loop, if we fetched JSON, reconstruct the response with all aggregated resources
        if first_response_json:
            if isinstance(first_response_json, dict):
                # Update the 'resources' or 'data' key with the aggregated list
                if "resources" in first_response_json and isinstance(first_response_json["resources"], list):
                    first_response_json["resources"] = all_resources_aggregated
                elif "data" in first_response_json and isinstance(first_response_json["data"], list):
                     first_response_json["data"] = all_resources_aggregated
                else: # If original response had no resources/data list, but we aggregated some
                    first_response_json["resources"] = all_resources_aggregated # Add it

                # Update pagination meta-information (optional, but good practice)
                first_response_json["next_page_url"] = None # Since we fetched all
                if "meta" in first_response_json and isinstance(first_response_json["meta"], dict):
                    first_response_json["meta"]["current_page"] = first_response_json["meta"].get("last_page", page_count)
                    # total might need to be updated if it was from first page only, but often it's the grand total
            else: # Should not happen if first_response_json was set from a dict
                 return all_resources_aggregated # Fallback: return list of resources if first_response_json wasn't a dict
            return first_response_json
        
        # If loop didn't run (e.g. initial target_path was None, though guarded earlier) or non-JSON on first page
        return None # Or raise error if no valid data could be returned
