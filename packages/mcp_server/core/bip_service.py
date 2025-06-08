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
    
    if not cookies_dict["bip_session"] or not cookies_dict["XSRF-TOKEN"]:
         raise HTTPException(status_code=400, detail="Essential BIP cookies missing from stored session data.")

    cookie_parts = []
    if cookies_dict.get("wiki_wiki_UserName"): cookie_parts.append(f"wiki_wiki_UserName={cookies_dict['wiki_wiki_UserName']}")
    if cookies_dict.get("wiki_wiki_UserID"): cookie_parts.append(f"wiki_wiki_UserID={cookies_dict['wiki_wiki_UserID']}")
    cookie_parts.append(f"XSRF-TOKEN={cookies_dict['XSRF-TOKEN']}")
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
