# packages/mcp_server/core/llm_service.py
import json
import google.generativeai as genai
from typing import Any, List, Dict, Optional # Added Optional
from ..config import settings
import os # For os.getenv
import asyncio # For rate limiting delays

# Configure the Google Generative AI client
try:
    # Check if the key from settings is a placeholder or actually missing
    api_key_to_configure = settings.GOOGLE_API_KEY
    if not api_key_to_configure or "YOUR_GOOGLE_API_KEY" in api_key_to_configure:
        env_api_key = os.getenv("GOOGLE_API_KEY")
        if env_api_key:
            api_key_to_configure = env_api_key
        # else: # Critical warning was here, but error will be raised by genai if key is bad
            # We can let genai.configure fail or handle it more gracefully,
            # for now, it will likely raise an error if api_key_to_configure is None or placeholder
    
    if api_key_to_configure and "YOUR_GOOGLE_API_KEY" not in api_key_to_configure:
        genai.configure(api_key=api_key_to_configure)
    # else: # Warning about not configured was here
        pass

except Exception as e:
    # Error configuring Google Generative AI client will be caught by individual calls if config fails
    pass

async def get_answer_from_llm(
    context_data: Any, 
    user_question: str, 
    query_details: Optional[Dict[str, Any]] = None, # New parameter
    model_name: str = "gemini-1.5-flash-latest"
) -> str:
    """
    Gets an answer from a Google Gemini model based on provided context data and a user question.
    If query_details indicates a search for specific_entity_details, it may exit early if an answer is found.
    """
    if not settings.GOOGLE_API_KEY or "YOUR_GOOGLE_API_KEY" in settings.GOOGLE_API_KEY:
        env_api_key = os.getenv("GOOGLE_API_KEY")
        if not env_api_key or "YOUR_GOOGLE_API_KEY" in env_api_key: # Double check env var too
            return "Error: GOOGLE_API_KEY not configured. Please set it in your .env file and restart."

    if not user_question:
        return "Error: No user question provided."

    try:
        model = genai.GenerativeModel(model_name)
    except Exception as e:
        return f"Error: Could not initialize AI model '{model_name}'. {str(e)}"

    # Define a target character length for each chunk's JSON string representation
    TARGET_CHUNK_CHAR_LENGTH = 28000 # Your suggestion, adjustable
    all_llm_answers = []

    # If context_data is not a list, or is a small list/dict, process as a single chunk
    if not isinstance(context_data, list) or not context_data:
        data_chunks = [context_data]
    else:
        # Attempt to split the list context_data into manageable chunks
        data_chunks = []
        current_chunk = []
        current_chunk_char_count = 0
        for item in context_data:
            try:
                item_str = json.dumps(item) # Estimate item size
                item_char_count = len(item_str)
            except TypeError: # Handle non-serializable items if they sneak in
                continue

            if current_chunk and (current_chunk_char_count + item_char_count > TARGET_CHUNK_CHAR_LENGTH):
                data_chunks.append(current_chunk)
                current_chunk = [item]
                current_chunk_char_count = item_char_count
            else:
                current_chunk.append(item)
                current_chunk_char_count += item_char_count
        
        if current_chunk: # Add the last remaining chunk
            data_chunks.append(current_chunk)
        
        if not data_chunks and context_data: # If context_data was not empty but chunking resulted in empty (e.g. all items non-serializable)
             data_chunks = [[]] # Send one empty list to signify no usable data

    for i, chunk in enumerate(data_chunks):
        try:
            if isinstance(chunk, (list, dict)):
                context_str_chunk = json.dumps(chunk, indent=2)
            else: # Should be a single non-list/dict item from the initial check
                context_str_chunk = str(chunk) 
        except Exception as e:
            all_llm_answers.append(f"[Error processing data chunk {i+1}: Could not serialize data]")
            continue
        
        # Note: MAX_CONTEXT_CHAR_LENGTH is now effectively TARGET_CHUNK_CHAR_LENGTH due to pre-chunking
        
        # Determine if the original question implies listing students from a department
        # This is a heuristic; a more robust way would be to pass intent from extract_query_type_and_value
        is_list_by_department_query = "list" in user_question.lower() and "student" in user_question.lower() and ("department" in user_question.lower() or "dept" in user_question.lower())
        
        # Construct a more targeted prompt if it's a list-by-department query
        if is_list_by_department_query:
            # Attempt to extract the department name from the original user question for the chunk prompt
            # This is a simplified extraction for the prompt context.
            # A more robust way would be to pass the already extracted department name.
            department_name_in_query = ""
            # Basic extraction - can be improved with regex or another LLM call if needed for precision here
            if "from " in user_question and " department" in user_question.lower():
                try:
                    start_index = user_question.lower().find("from ") + 5
                    end_index = user_question.lower().find(" department")
                    department_name_in_query = user_question[start_index:end_index].strip()
                except:
                    pass # Fallback to generic prompt part

            prompt_parts = [
                f"The user's original question was to list students from a department (likely '{department_name_in_query}').",
                "Based ONLY on the student data CHUNK provided below, list the full names of all students who match this department query.",
                "Each name should be on a new line. If no students in this CHUNK match, respond with the exact phrase: NO_MATCHING_STUDENTS_IN_CHUNK",
                "\nProvided data CHUNK:\n",
                context_str_chunk
            ]
        else: # Original generic prompt for other types of questions
            prompt_parts = [
                "You are an AI assistant for the BIP (BIT Information Portal). You will be provided with a chunk of data extracted from the BIP system in JSON format and a user's question about this data.",
                "Your task is to answer the user's question based *only* on the provided data chunk. Focus only on the data given in this specific chunk.",
                "If the question asks for a list (e.g., 'List all students'), provide the relevant items from THIS CHUNK ONLY.",
                "Do not make up information or answer questions outside the scope of the given data chunk.",
                "If the data chunk does not contain the answer, clearly state that the information is not available in this specific data chunk or provide an empty list if appropriate for a listing question.",
                "Be concise.",
                "\nProvided data CHUNK:\n",
                context_str_chunk,
                "\nUser's original question (answer based on the CHUNK above):\n",
                user_question
            ]

        try:
            response = await model.generate_content_async(prompt_parts)
            
            if not response.candidates or not response.candidates[0].content.parts:
                 all_llm_answers.append(f"[No answer from AI for data chunk {i+1}]")
                 continue

            chunk_answer_parts = [part.text for part in response.candidates[0].content.parts if hasattr(part, 'text')]
            chunk_answer = "".join(chunk_answer_parts).strip()
            
            if not chunk_answer:
                if response.prompt_feedback and response.prompt_feedback.block_reason:
                    block_reason_message = response.prompt_feedback.block_reason_message or "No specific reason provided."
                    all_llm_answers.append(f"[AI content generation blocked for chunk {i+1}: {block_reason_message}]")
                else:
                    all_llm_answers.append(f"[Empty response from AI for data chunk {i+1}]") # Or specific handling for "list" questions
            else:
                all_llm_answers.append(chunk_answer)
            
            # Early exit for specific_entity_details if a satisfactory answer is found in a chunk
            if query_details and query_details.get("type") == "specific_entity_details":
                # Heuristic: if the answer is not a generic "not found" and seems substantial.
                # A more robust check might involve another LLM call to verify if chunk_answer answers user_question.
                if chunk_answer and \
                   "not found" not in chunk_answer.lower() and \
                   "not available" not in chunk_answer.lower() and \
                   "no_matching" not in chunk_answer.upper() and \
                   len(chunk_answer) > 20: # Arbitrary length to suggest a real answer
                    # We take this chunk's answer as the final one for this specific query type.
                    # Need to clear other collected answers if any, or just use this one.
                    # For simplicity, let's assume this is THE answer.
                    return chunk_answer # Exit early

            if len(data_chunks) > 1 and i < len(data_chunks) - 1: # Add delay if there are more chunks
                await asyncio.sleep(4)

        except Exception as e: 
            error_detail = str(e)
            if hasattr(e, 'message'): error_detail = e.message
            elif hasattr(e, 'args') and e.args: error_detail = str(e.args[0])
            all_llm_answers.append(f"[Error contacting AI for data chunk {i+1}: {error_detail}]")

    # Combine answers from all chunks.
    collected_names = set() # Use a set to store names to avoid duplicates if any chunk overlaps or LLM repeats
    has_actual_content = False
    
    # Determine if the original question implies listing students from a department (heuristic, same as above)
    is_list_by_department_query_for_aggregation = "list" in user_question.lower() and "student" in user_question.lower() and ("department" in user_question.lower() or "dept" in user_question.lower())

    for ans_from_chunk in all_llm_answers:
        if ans_from_chunk and \
           not ans_from_chunk.startswith("[Error") and \
           not ans_from_chunk.startswith("[No answer") and \
           not ans_from_chunk.startswith("[Empty response") and \
           not ans_from_chunk.startswith("[AI content generation blocked") and \
           ans_from_chunk != "NO_MATCHING_STUDENTS_IN_CHUNK":
            
            has_actual_content = True
            if is_list_by_department_query_for_aggregation:
                # Assuming LLM returns names separated by newlines or commas for list queries
                names_in_chunk = [name.strip() for name in ans_from_chunk.replace(",", "\n").split("\n") if name.strip()]
                for name in names_in_chunk:
                    collected_names.add(name)
            else:
                # For non-list queries, just append the whole answer (might need better strategy for other question types)
                collected_names.add(ans_from_chunk) # Using set here might be odd for non-list answers

    if is_list_by_department_query_for_aggregation:
        if collected_names:
            final_answer = "\n".join(sorted(list(collected_names)))
        elif has_actual_content: # Some chunks responded, but all were "NO_MATCHING..."
             final_answer = "No students found matching your criteria in the provided data."
        else: # All chunks resulted in errors or no content
            final_answer = "Could not retrieve a student list. Issues encountered while processing data."
    else: # For non-list queries
        if collected_names: # Should ideally be just one item in the set for non-list queries
            final_answer = "\n".join(sorted(list(collected_names))) 
        elif has_actual_content: # Some chunks responded but not with usable answer
            final_answer = "The AI assistant processed the data but could not formulate a specific answer."
        else:
            final_answer = "Could not retrieve an answer. Issues encountered while processing data chunks."


    if not final_answer.strip() and not has_actual_content : # No chunks or all chunks were empty and yielded no answer
        final_answer = "No information found in the provided data to answer the question."

    return final_answer.strip() if final_answer else "No answer could be formulated based on the provided data."


async def determine_api_path_from_query(user_question: str, available_apis: List[Dict[str, str]], model_name: str = "gemini-1.5-flash-latest") -> str | None:
    """
    Determines the most appropriate API path to call based on the user's question and a list of available APIs.
    Returns the API path string or None if no suitable path is found or an error occurs.
    """
    if not settings.GOOGLE_API_KEY or "YOUR_GOOGLE_API_KEY" in settings.GOOGLE_API_KEY:
        env_api_key = os.getenv("GOOGLE_API_KEY")
        if not env_api_key or "YOUR_GOOGLE_API_KEY" in env_api_key:
            return None

    if not user_question:
        return None
    if not available_apis:
        return None

    try:
        model = genai.GenerativeModel(model_name)
    except Exception as e:
        return None

    formatted_apis = "\n".join([
        f"{i+1}. Path: {api['path']}\n   Description: {api['description']}\n   Data Hint: {api.get('data_schema_hint', 'N/A')}" 
        for i, api in enumerate(available_apis)
    ])

    prompt = f"""Your task is to select the single most appropriate API endpoint path from the provided list to answer the user's question.
The API endpoints provide different types of student academic data.
Respond with ONLY the API path string (e.g., "/nova-api/students").
If no listed API endpoint can answer the question, respond with "NO_PATH_FOUND".

Available API Endpoints:
{formatted_apis}

User's Question: "{user_question}"

Selected API Path:"""

    try:
        response = await model.generate_content_async(prompt)

        if not response.candidates or not response.candidates[0].content.parts:
            return None
        
        selected_path = "".join([part.text for part in response.candidates[0].content.parts if hasattr(part, 'text')]).strip()
        
        if selected_path == "NO_PATH_FOUND":
            return None
        
        valid_paths = [api['path'] for api in available_apis]
        if selected_path in valid_paths:
            return selected_path
        else:
            return None
    except Exception as e:
        return None

async def extract_searchable_identifier_from_student_query(user_question: str, model_name: str = "gemini-1.5-flash-latest") -> str | None:
    """
    Attempts to extract a primary student identifier (name, roll number, or registration number) 
    from a user question if it seems to be asking about a specific student.
    Returns the extracted identifier string or None.
    """
    if not settings.GOOGLE_API_KEY or "YOUR_GOOGLE_API_KEY" in settings.GOOGLE_API_KEY:
        env_api_key = os.getenv("GOOGLE_API_KEY")
        if not env_api_key or "YOUR_GOOGLE_API_KEY" in env_api_key:
            return None
    
    try:
        model = genai.GenerativeModel(model_name)
    except Exception as e:
        return None

    prompt = f"""Your task is to extract a specific student identifier from the user's question.
A student identifier is typically a unique value like a full name (e.g., "JOHN DOE"), a roll number (e.g., "7376222AL219"), or a registration/enrollment number (e.g., "2022UAD001").
Do NOT extract department names, course names, or other general categories as identifiers.
If a clear, specific student identifier is found, respond with ONLY that identifier value.
If the question is asking for a list of students based on a general criteria (like department or course), or if no specific student identifier is mentioned, respond with "NO_SPECIFIC_IDENTIFIER_FOUND".

User's Question: "{user_question}"

Extracted Identifier:"""

    try:
        response = await model.generate_content_async(prompt)
        
        if not response.candidates or not response.candidates[0].content.parts:
            return None
        
        extracted_text = "".join([part.text for part in response.candidates[0].content.parts if hasattr(part, 'text')]).strip()
        
        if extracted_text.upper() == "NO_SPECIFIC_IDENTIFIER_FOUND" or not extracted_text: # Updated keyword
            return None
        # Basic validation: check if it's not overly long or just noise, though LLM should handle this.
        if len(extracted_text) > 100: # Arbitrary limit to avoid very long erroneous extractions
            return None
        return extracted_text

    except Exception as e:
        return None

async def extract_query_type_and_value(user_question: str, model_name: str = "gemini-1.5-flash-latest") -> Dict[str, str] | None:
    """
    Determines if the user question is asking for a specific student by identifier (name, roll, reg_no),
    or listing students by department, or a general query for the students API.
    Returns a dict like:
    {"type": "identifier", "value": "STUDENT_ID_VALUE"}
    {"type": "department_name", "value": "DEPARTMENT_NAME"}
    {"type": "general_listing", "value": null}
    or None if error.
    """
    if not settings.GOOGLE_API_KEY or "YOUR_GOOGLE_API_KEY" in settings.GOOGLE_API_KEY:
        env_api_key = os.getenv("GOOGLE_API_KEY")
        if not env_api_key or "YOUR_GOOGLE_API_KEY" in env_api_key:
            return None
    
    try:
        model = genai.GenerativeModel(model_name)
    except Exception as e:
        return None

    prompt = f"""Analyze the user's question. Your goal is to determine the query type and extract a key value if applicable.
The query types are: "specific_entity_details", "list_by_category", or "general_listing".

1.  **"specific_entity_details"**: The question asks for details about a *single, specific, named item*.
    *   This could be a student identified by full name, roll number, or registration number.
    *   This could ALSO be a specific event or activity identified by its unique or commonly known name (e.g., "STARTIFY 3.0", "NIDAR 2025", "She Hacks Hackathon").
    *   Keywords often include: "who is [STUDENT_NAME]?", "details of student [ROLL_NO]", "tell me about [EVENT_NAME]", "what are the details for [EVENT_NAME]?".
    *   If a specific student identifier OR a specific event name is found, respond: {{"type": "specific_entity_details", "value": "THE_EXTRACTED_NAME_OR_ID"}}
    *   **Crucial for Events:** If the question is "Tell me about the event STARTIFY 3.0", the value should be "STARTIFY 3.0".
    *   Example for "Who is Venkatkumar M?": {{"type": "specific_entity_details", "value": "Venkatkumar M"}}
    *   Example for "Tell me about the STARTIFY 3.0 event": {{"type": "specific_entity_details", "value": "STARTIFY 3.0"}}
    *   Example for "What is STARTIFY 3.0?": {{"type": "specific_entity_details", "value": "STARTIFY 3.0"}}
    *   Example for "Details for roll number 7376222AL219": {{"type": "specific_entity_details", "value": "7376222AL219"}}
    *   Example for "information about NIDAR 2025": {{"type": "specific_entity_details", "value": "NIDAR 2025"}}

2.  **"list_by_category"**: The question asks for a *list of items based on a category*.
    *   For students, the category is usually 'department_name'.
    *   For student activities/events, the category could be 'event_category' (e.g., "hackathon", "workshop"), 'organizer', or 'location'.
    *   Keywords: "list students from", "events in category X", "hackathons available", "events at [LOCATION]".
    *   If a category and its value are found, respond: {{"type": "list_by_category", "category_type": "department_name" (or "event_category", "organizer", "location"), "value": "THE_CATEGORY_VALUE"}}
    *   Example for "List students from Artificial Intelligence and Machine Learning department": {{"type": "list_by_category", "category_type": "department_name", "value": "Artificial Intelligence and Machine Learning"}}
    *   Example for "Are there any hackathons?": {{"type": "list_by_category", "category_type": "event_category", "value": "Hackathon"}}
    *   Example for "Events happening in KCT": {{"type": "list_by_category", "category_type": "location", "value": "KCT"}}

3.  **"general_listing"**: The question is a general request for a list from an endpoint (e.g., "What student activities are available?", "Show some students."), or no specific identifier/category is clearly mentioned.
    *   Respond: {{"type": "general_listing", "value": null}}

Instructions for extraction:
-   Be precise. Only extract full, clear identifiers, names, or category values.
-   **If the question is about a specific named entity (e.g., "Tell me about event X", "Who is student Y?"), ALWAYS classify it as "specific_entity_details" and extract the entity name/ID as the value.** Do NOT classify these as "general_listing" or "list_by_category".
-   Use "list_by_category" only when the user asks for a list based on a general category type (e.g., "list all hackathons", "students in the CS department").
-   If the question is very broad (e.g., "What can you do?", "Show me some activities") and does not mention any specific entity or category, then use "general_listing".
-   Prioritize "specific_entity_details" if a clear entity name/ID is present.

User's Question: "{user_question}"

Respond with ONLY the JSON object:"""

    try:
        response = await model.generate_content_async(prompt)
        
        if not response.candidates or not response.candidates[0].content.parts:
            return None
        
        extracted_text = "".join([part.text for part in response.candidates[0].content.parts if hasattr(part, 'text')]).strip()

        # Clean the response to ensure it's valid JSON
        # Remove potential markdown backticks if LLM wraps JSON in them
        if extracted_text.startswith("```json"):
            extracted_text = extracted_text[7:]
        if extracted_text.startswith("```"):
            extracted_text = extracted_text[3:]
        if extracted_text.endswith("```"):
            extracted_text = extracted_text[:-3]
        extracted_text = extracted_text.strip()

        try:
            result_json = json.loads(extracted_text)
            if isinstance(result_json, dict) and "type" in result_json: # Value might be null for general_listing
                # Basic validation of types
                # Updated list of allowed types
                if result_json["type"] in ["specific_entity_details", "list_by_category", "general_listing"]:
                    # Ensure 'value' exists, except for general_listing where it should be null
                    if result_json["type"] == "general_listing":
                        result_json["value"] = None # Enforce null for general_listing
                    elif "value" not in result_json or not isinstance(result_json["value"], str):
                        # For specific_entity_details and list_by_category (if value is expected string)
                        if result_json["type"] == "list_by_category" and "category_type" in result_json and result_json.get("value") is None:
                            # Allow null value for list_by_category if category_type implies it (e.g. "list all hackathons" might have value "Hackathon" or null if just "list hackathons")
                            # This needs careful thought if value can be optional for list_by_category.
                            # For now, assume value is required if not general_listing.
                            pass # Allow if category_type is present and value is None (e.g. list all of a category type)
                        elif not ("value" in result_json and isinstance(result_json.get("value"), str)):
                            return {"type": "general_listing", "value": None} # Fallback
                    
                    # Ensure 'category_type' exists if type is 'list_by_category'
                    if result_json["type"] == "list_by_category" and "category_type" not in result_json:
                        return {"type": "general_listing", "value": None} # Fallback

                    return result_json
                # else: # LLM returned unexpected type
            # else: # LLM response is not a valid JSON with 'type' and 'value'
                pass # Fall through to JSONDecodeError or general fallback

        except json.JSONDecodeError:
            # If it's not JSON, but a simple string like "NO_IDENTIFIER_FOUND" or just the value, try to handle common old patterns
            if extracted_text.upper() == "NO_SPECIFIC_IDENTIFIER_FOUND" or \
               extracted_text.upper() == "NO_IDENTIFIER_FOUND" or \
               extracted_text.upper() == "GENERAL_LISTING":
                return {"type": "general_listing", "value": None}
            # If it's just a string, assume it's an identifier if it's not too long (heuristic)
            if isinstance(extracted_text, str) and 0 < len(extracted_text) <= 100:
                 return {"type": "identifier", "value": extracted_text} # This was "identifier", but prompt asks for specific_entity_details

        return {"type": "general_listing", "value": None} # Fallback if parsing fails or unexpected

    except Exception as e:
        return None
