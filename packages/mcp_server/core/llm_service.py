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
            department_name_in_query = ""
            if "from " in user_question and " department" in user_question.lower():
                try:
                    start_index = user_question.lower().find("from ") + 5
                    end_index = user_question.lower().find(" department")
                    department_name_in_query = user_question[start_index:end_index].strip()
                except: pass

            prompt_parts = [
                f"You're a helpful and slightly witty AI assistant for the BIP. The user wants a list of students, likely from the '{department_name_in_query}' department.",
                "Based ONLY on this CHUNK of student data, list the full names of students matching the department query.",
                "Each name on a new line, please! If this chunk is a dud (no matches), just say: NO_MATCHING_STUDENTS_IN_CHUNK",
                "\nProvided data CHUNK:\n",
                context_str_chunk
            ]
        elif query_details and query_details.get("type") == "multi_entity_comparison":
            entities_info = query_details.get("entities", []) # This is a list of dicts
            entity_names_list = [info.get("name", "Unknown Entity") for info in entities_info if isinstance(info, dict)]
            entity_list_str = " and ".join(entity_names_list)
            prompt_parts = [
                f"You are an AI assistant. The user asked: \"{user_question}\"",
                f"You have been provided with data for the following individuals: {entity_list_str}.",
                "Based ONLY on the provided data for these individuals:",
                "1. Briefly state what type of individuals they are if common (e.g., 'Both are students', 'One is a faculty and one is a student').",
                "2. Describe any other specific relationships or significant commonalities found in their data (e.g., same department, enrolled in the same course, part of the same project).",
                "3. If no specific relationship or significant commonality beyond their general type is found, clearly state that.",
                "Keep your answer concise and informative. Maintain a helpful and slightly witty tone.",
                "\nProvided data (this is a single CHUNK containing all fetched profiles/data for the entities):\n",
                context_str_chunk # For multi-entity, context_str_chunk will contain the list of profiles
            ]
        elif query_details and query_details.get("type") == "specific_entity_details":
             entity_name = query_details.get("value", "that specific thing")
             prompt_parts = [
                f"Alright, you're the BIP's top info-detective! The user is asking about '{user_question}'.",
                f"Focus on finding details about '{entity_name}' in this CHUNK of data.",
                "Answer based *only* on the provided data chunk. Be clear, and if you can, a little bit charming (but still professional!).",
                "If the specific info isn't in this chunk, say something like 'Hmm, can't find details for {entity_name} in this bit of data.'",
                "\nProvided data CHUNK:\n",
                context_str_chunk,
                "\nUser's question (answer from CHUNK only):\n",
                user_question
             ]
        else: # Original generic prompt for other types of questions, with a touch of personality
            prompt_parts = [
                "You are a friendly and helpful AI assistant for the BIP (BIT Information Portal), with a knack for being clear and maybe a little bit fun.",
                "You'll get a chunk of data from BIP and a user's question.",
                "Your mission, should you choose to accept it, is to answer based *only* on the data in THIS CHUNK.",
                "No outside knowledge, no guessing! If the info isn't in the chunk, just say so (e.g., 'Sorry, that info isn't in this slice of data!').",
                "If it's a list they want, list items from this chunk. Keep it concise but human.",
                "\nProvided data CHUNK:\n",
                context_str_chunk,
                "\nUser's original question (answer based on the CHUNK above):\n",
                user_question
            ]
        
        print(f"--- Debug LLM Answering: Sending request to Gemini for chunk {i+1}/{len(data_chunks)}. Model: {model_name}.")
        # For very verbose debugging, you could print the full prompt_parts, but be wary of log size.
        # print(f"--- Debug LLM Answering: Prompt for chunk {i+1}: {prompt_parts}")


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

    # --- Aggregation and Synthesis Logic ---
    final_answer = "No answer could be formulated based on the provided data." # Default
    
    answers_with_content = []
    for ans_from_chunk in all_llm_answers:
        if ans_from_chunk and \
           not ans_from_chunk.startswith("[Error") and \
           not ans_from_chunk.startswith("[No answer") and \
           not ans_from_chunk.startswith("[Empty response") and \
           not ans_from_chunk.startswith("[AI content generation blocked") and \
           ans_from_chunk.upper() != "NO_MATCHING_STUDENTS_IN_CHUNK": # Case-insensitive check
            answers_with_content.append(ans_from_chunk.strip())

    if not answers_with_content:
        return "No relevant information found in the data to answer your question."

    # Determine if this is a simple list aggregation query (e.g., list students by dept)
    # This relies on the query_details passed into this function.
    is_simple_list_aggregation = (
        query_details and
        query_details.get("type") == "list_by_category" and
        query_details.get("category_type") == "department_name"
    )
    # Add other query types that should be simple list aggregations here if needed.

    if len(answers_with_content) > 1 and not is_simple_list_aggregation:
        print(f"--- Synthesizing final answer from {len(answers_with_content)} chunks for question: '{user_question}' ---")
        combined_text_for_synthesis = "\n\n==== NEXT PIECE OF INFORMATION ====\n\n".join(answers_with_content)
        
        synthesis_prompt_parts = [
            "You are an expert AI assistant tasked with synthesizing information.",
            f"The user's original question was: \"{user_question}\"",
            "The following are several pieces of information that were retrieved in response to this question, possibly from different segments of a larger dataset.",
            "Your goal is to combine these pieces into a single, coherent, and comprehensive natural language answer.",
            "Key instructions for synthesis:",
            "- Ensure the final answer directly addresses the user's original question.",
            "- Avoid redundancy. If multiple pieces say the same thing, consolidate it.",
            "- Maintain a helpful, clear, and slightly witty/human-like tone.",
            "- Do NOT mention that the information came from different 'chunks', 'pieces', or 'segments'. Present it as one unified response.",
            "- If the information pieces cover distinct aspects or topics related to the question, organize them logically in your answer.",
            "- If there are minor contradictions, try to present the information factually or acknowledge the differing details if significant and unavoidable.",
            "\nCombined Information Pieces (separated by '==== NEXT PIECE OF INFORMATION ===='):\n",
            combined_text_for_synthesis
        ]
        try:
            # Assuming 'model' is still the genai.GenerativeModel instance from earlier in the function
            synthesis_response = await model.generate_content_async(synthesis_prompt_parts)
            if synthesis_response.candidates and synthesis_response.candidates[0].content.parts:
                final_answer = "".join([part.text for part in synthesis_response.candidates[0].content.parts if hasattr(part, 'text')]).strip()
                if not final_answer.strip(): # If LLM returns empty string
                    print("Warning: Synthesis LLM call returned empty content. Falling back to joining chunk answers.")
                    final_answer = "\n\n".join(answers_with_content) # Fallback
            else:
                print("Warning: Synthesis LLM call failed or returned no candidates/parts. Falling back to joining chunk answers.")
                final_answer = "\n\n".join(answers_with_content) # Fallback
        except Exception as e_synth:
            print(f"Error during synthesis LLM call: {e_synth}. Falling back to joining chunk answers.")
            final_answer = "\n\n".join(answers_with_content) # Fallback
    
    elif is_simple_list_aggregation:
        # For simple list aggregation (e.g., student names by department)
        # The per-chunk prompt for these should ideally return just the list items.
        collected_items_for_list = set()
        for ans_item_list_str in answers_with_content:
            # Assuming LLM returns names/items separated by newlines for list queries
            items_in_chunk = [name.strip() for name in ans_item_list_str.split("\n") if name.strip() and name.upper() != "NO_MATCHING_STUDENTS_IN_CHUNK"]
            for item_in_list in items_in_chunk:
                collected_items_for_list.add(item_in_list)
        
        if collected_items_for_list:
            final_answer = "\n".join(sorted(list(collected_items_for_list)))
        else:
            final_answer = "No items found matching your criteria in the provided data."
    else: # Only one chunk with content, or synthesis not needed (e.g. simple list with 1 chunk)
        final_answer = "\n\n".join(answers_with_content) # Join if multiple (though this path implies 1), or just the single answer

    return final_answer.strip() if final_answer.strip() else "No answer could be formulated based on the provided data."


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

    Consider the following:
    - If the user's question uses possessive terms like "my" (e.g., "my achievements", "my feedback", "my details"), prioritize API endpoints whose descriptions align with personal data retrieval for the logged-in user.
    - Match keywords from the question to the API descriptions and data schema hints.

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

3.  **"general_listing"**: The question is a general request for a list from an endpoint, or no specific identifier/category is clearly mentioned.
    *   If the question contains potential keywords that could be used for a general search (but aren't specific entities or categories already handled), extract them.
    *   Example: "Show me student achievements related to hackathons and AI" -> {{"type": "general_listing", "value": "hackathons AI"}}
    *   Example: "What student activities are available?" -> {{"type": "general_listing", "value": null}}
    *   Example: "Show some students." -> {{"type": "general_listing", "value": null}}
    *   Respond: {{"type": "general_listing", "value": "EXTRACTED_KEYWORDS_AS_STRING_OR_NULL"}}

4.  **"user_context_dependent_query"**: The question requires information about the logged-in user's context (like their department or current courses) to be resolved before querying a data endpoint.
    *   Keywords: "faculties teaching me", "my teachers", "my current course faculty", "professors for my courses".
    *   If such a query is identified, respond: {{"type": "user_context_dependent_query", "sub_type": "faculty_for_my_courses", "value": null}} (Value is null as the resolution logic will handle specifics).
    *   Example for "Faculties teaching me": {{"type": "user_context_dependent_query", "sub_type": "faculty_for_my_courses", "value": null}}

5.  **"multi_entity_comparison"**: The question asks about a relationship, comparison, or commonalities between two or more named entities.
    *   Keywords: "relation between X and Y", "compare X and Y", "do X and Y have anything in common", "are X and Y in the same department".
    *   Extract the named entities. If the user specifies a type for an entity (e.g., "Ezhil (faculty)", "Venkatkumar (student)"), extract the type as well. Valid types are "student", "faculty", "course", "department", "event". If no type is specified, the type can be null or omitted.
    *   Respond: {{"type": "multi_entity_comparison", "entities": [{{"name": "ENTITY1_NAME", "type": "ENTITY1_TYPE_OR_NULL"}}, {{"name": "ENTITY2_NAME", "type": "ENTITY2_TYPE_OR_NULL"}}, ...], "value": "BRIEF_DESCRIPTION_OF_COMPARISON_TYPE_IF_OBVIOUS_ELSE_NULL"}}
    *   Example for "Is there any relation between Venkatkumar and Thanushri?": {{"type": "multi_entity_comparison", "entities": [{{"name": "Venkatkumar", "type": null}}, {{"name": "Thanushri", "type": null}}], "value": "general relation"}}
    *   Example for "Are Venkatkumar and Thanushri in the same department?": {{"type": "multi_entity_comparison", "entities": [{{"name": "Venkatkumar", "type": null}}, {{"name": "Thanushri", "type": null}}], "value": "same department check"}}
    *   Example for "Who is Ezhil R (faculty) to Venkatkumar M (student)?": {{"type": "multi_entity_comparison", "entities": [{{"name": "Ezhil R", "type": "faculty"}}, {{"name": "Venkatkumar M", "type": "student"}}], "value": "general relation"}}

Instructions for extraction:
-   Be precise. Only extract full, clear identifiers, names, or category values.
-   **The user may make typos or grammatical errors. Try to understand their intent despite these errors.** For example, if they ask "who is venkatkumr m?", you should still recognize "venkatkumr m" as an attempt at a name.
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
                if result_json["type"] in ["specific_entity_details", "list_by_category", "general_listing", "user_context_dependent_query", "multi_entity_comparison"]:
                    # Ensure 'value' exists and is appropriate for the type
                    if result_json["type"] == "general_listing" or result_json["type"] == "user_context_dependent_query":
                        if "value" in result_json and not (isinstance(result_json.get("value"), str) or result_json.get("value") is None):
                            result_json["value"] = None 
                        elif "value" not in result_json:
                             result_json["value"] = None
                        if result_json["type"] == "user_context_dependent_query" and "sub_type" not in result_json:
                            print(f"Warning: 'user_context_dependent_query' missing 'sub_type'. Falling back.")
                            return {"type": "general_listing", "value": None}
                    elif result_json["type"] == "multi_entity_comparison":
                        if "entities" not in result_json or not isinstance(result_json["entities"], list) or not result_json["entities"]:
                            print(f"Warning: 'multi_entity_comparison' missing or invalid 'entities' list. Falling back.")
                            return {"type": "general_listing", "value": None}
                        # Validate structure of each entity in the list
                        for entity_item in result_json["entities"]:
                            if not isinstance(entity_item, dict) or "name" not in entity_item:
                                print(f"Warning: Invalid entity item in 'multi_entity_comparison': {entity_item}. Falling back.")
                                return {"type": "general_listing", "value": None}
                            if "type" not in entity_item: # Ensure type key exists, can be null
                                entity_item["type"] = None
                        if "value" not in result_json: 
                            result_json["value"] = None
                    elif "value" not in result_json or not isinstance(result_json["value"], str):
                        if result_json["type"] == "list_by_category" and "category_type" in result_json and result_json.get("value") is None:
                            pass 
                        elif not ("value" in result_json and isinstance(result_json.get("value"), str)):
                            return {"type": "general_listing", "value": None} 
                    
                    if result_json["type"] == "list_by_category" and "category_type" not in result_json:
                        return {"type": "general_listing", "value": None} 

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
