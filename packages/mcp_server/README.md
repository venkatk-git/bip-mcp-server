# MCP Server (`packages/mcp_server`) - Detailed Flow

This document outlines the detailed request lifecycle and internal logic of the `mcp_server`, particularly focusing on the `/assistant/ask` endpoint, which powers the AI assistant.

## Core Objective

The primary goal of the `/assistant/ask` endpoint is to take a user's natural language question, intelligently query the relevant BIP (BIT Information Portal) API(s), and return a synthesized, human-readable answer based on the retrieved data.

## Request Lifecycle for `/assistant/ask`

The following steps describe the journey of a user's question through the server:

1.  **Request Reception (`routes/assistant_routes.py -> ask_bip_data_with_llm`)**:
    *   The endpoint receives a POST request with a JSON body containing `user_question` (and optional `target_bip_api_path`, `item_id`).
    *   The user's question is normalized (converted to lowercase) for some initial checks.

2.  **Initial Path Determination Strategy (if `target_bip_api_path` is not provided by user)**:
    The system employs a multi-stage strategy to determine which BIP API endpoint to target:

    *   **a. User Context Dependent Query Check (`extract_query_type_and_value` then conditional logic):**
        *   The user's question is first sent to an LLM (`extract_query_type_and_value` in `core/llm_service.py`).
        *   This LLM attempts to classify the query. If it identifies the query as `{"type": "user_context_dependent_query", "sub_type": "faculty_for_my_courses"}` (e.g., for "Faculties teaching me"):
            *   Control is transferred to a dedicated handler: `handle_faculty_for_my_courses_query`.
            *   **`handle_faculty_for_my_courses_query` Flow:**
                1.  Calls `get_student_details_from_session` (`core/bip_service.py`) to fetch the logged-in student's ID, department ID, department name, and current semester using BIP session cookies. This involves an API call to `/nova-api/students/{id}` or `/nova-api/students?search=...`.
                2.  If student details are found, it constructs parameters to fetch data from `/nova-api/academic-course-faculty-mappings` (currently a broad fetch with default filters).
                3.  The retrieved course-faculty mappings are then filtered in Python to match the student's specific department and semester.
                4.  This filtered data is passed to `get_answer_from_llm` along with the original user question to generate the final answer.
                5.  The response is returned, bypassing the main path selection logic below.
            *   If the `sub_type` is unknown, it logs a message and proceeds to the next step.

    *   **b. Rule-Based Keyword Override (Fuzzy Matching):**
        *   If the query was not handled by a user context-dependent flow, it's checked against a predefined list of `achievement_keywords` (e.g., "my achievement", "my participation").
        *   This check now uses fuzzy matching (`thefuzz.partial_ratio`) with a threshold (e.g., 90%) to tolerate minor typos in the keywords (e.g., "my acheivements").
        *   If a fuzzy match is found, `base_effective_path` is forced to `/nova-api/student-achievement-loggers`.

    *   **c. LLM-Based Path Selection (`determine_api_path_from_query`):**
        *   If no rule-based override occurs, the user's question is sent to another LLM (`determine_api_path_from_query` in `core/llm_service.py`).
        *   This LLM is provided with a list of all registered BIP API endpoints and their descriptions from `core/bip_api_registry.py`.
        *   The LLM selects the most appropriate `base_effective_path` or returns "NO_PATH_FOUND".
        *   If no path is found, an error message is returned to the user.

3.  **Query Parameterization (`routes/assistant_routes.py -> ask_bip_data_with_llm`)**:
    *   Once `base_effective_path` is determined (either by user input, rule, or LLM), the system uses the `query_details` obtained from `extract_query_type_and_value` (which was called at the beginning of the path determination phase, and its result stored as `query_details_for_llm`). This includes:
        *   `type`: e.g., "specific_entity_details", "list_by_category", "general_listing", "user_context_dependent_query".
        *   `value`: The extracted entity name, category value, or search keywords.
        *   `category_type`: e.g., "department_name", "event_category".
    *   Based on `base_effective_path` and these `query_details`, API parameters (`api_params`) are constructed:
        *   **`/nova-api/students`**:
            *   If `specific_entity_details`: `search` parameter is set to the student name/ID. `should_fetch_all_pages = False`.
            *   If `list_by_category` (department): `get_department_id_by_name` is called (uses cached department list from `/nova-api/departments`), and a `filters` parameter is constructed for the department ID. `perPage=150`, `should_fetch_all_pages = True`.
            *   Otherwise (general list): `perPage=150`, `should_fetch_all_pages = True`.
        *   **`/nova-api/student-activity-masters`**:
            *   If `specific_entity_details` (event name): `search` is set to event name, default empty `filters` are applied. `should_fetch_all_pages = False`.
            *   If `list_by_category` (event_category, location, organizer): `search` is set to category value. `perPage=150`, `should_fetch_all_pages = True`.
            *   If `general_listing` with keywords: `search` is set to keywords. `perPage=150`, `should_fetch_all_pages = True`.
            *   Otherwise: `perPage=150`, `should_fetch_all_pages = True`.
        *   **General Endpoints (e.g., `/academic-feedbacks`, `/departments`, `/student-achievement-loggers`, `/academic-course-faculty-mappings`, `/periodical-statuses`)**:
            *   If `general_listing` with keywords: `search` is set to keywords.
            *   `perPage=150`, `should_fetch_all_pages = True`.
            *   **Default Filters**: For specific paths like `/student-achievement-loggers`, `/academic-course-faculty-mappings`, and `/periodical-statuses`, predefined default empty `filters` are applied if no other filters are present. This ensures the API behaves as expected based on observed cURL patterns.
        *   **Other Paths**: Default to single-page fetch if not explicitly configured for multi-page.

4.  **Data Fetching (`core/bip_service.py -> fetch_bip_data`)**:
    *   The constructed `final_api_path_with_params` is used.
    *   BIP session cookies (including `bip_session`, `XSRF-TOKEN`, `wiki_wiki_UserID`, `wiki_wiki_UserName`, and the recently added `app_forward_auth`) are retrieved from the server-side session (`request.session['bip_session_data']`) and added to the request headers.
    *   An `httpx.AsyncClient` makes the GET request to the BIP API.
    *   **Pagination Handling**: If `should_fetch_all_pages` is true, the function checks for `next_page_url` in the API response and iteratively fetches subsequent pages (up to a safety limit, e.g., 5 pages) to aggregate results.
    *   Handles HTTP errors, session expiry (redirects to login), and JSON decoding errors.

5.  **Data Parsing (`routes/assistant_routes.py -> parse_nova_api_response_data`)**:
    *   The raw JSON response from `fetch_bip_data` is passed to this parser.
    *   It's designed for typical Nova API structures, extracting data from `resources` (or `data` for single items) lists, and then from `id`, `attributes`, or `fields` within each resource item.
    *   The goal is to create a cleaner, more uniform list of dictionaries.

6.  **Item ID Filtering (if `item_id` is provided by user)**:
    *   If an `item_id` was part of the initial request, the `parsed_data` is filtered to include only the item matching that ID.

7.  **Answer Generation (`core/llm_service.py -> get_answer_from_llm`)**:
    *   The (potentially filtered) `parsed_data` and the original `user_question` (along with `query_details`) are sent to the answering LLM.
    *   **Chunking**: If `parsed_data` is large, it's split into smaller JSON string chunks (e.g., ~28,000 characters each) to fit within the LLM's context window.
    *   **Per-Chunk LLM Call**: The LLM is called for each chunk with a prompt tailored to the query type (e.g., specific entity detail search, list generation, or general summarization).
    *   **Early Exit for Specific Details**: If `query_details` indicates a search for a specific entity and a satisfactory answer is found in an early chunk, the process can exit early.
    *   **Answer Synthesis**:
        *   If multiple chunks produce valid content and the query isn't a simple list aggregation (like "list students by department"), an additional LLM call is made.
        *   This "synthesis LLM call" takes all chunk answers and a prompt instructing it to combine them into a single, coherent, non-redundant response, maintaining the desired tone.
        *   If synthesis fails or is not needed (e.g., single chunk answer, or simple list aggregation), the chunk answers are joined appropriately.
    *   The final text from the LLM is returned.

8.  **Response to User (`routes/assistant_routes.py -> ask_bip_data_with_llm`)**:
    *   The synthesized/final answer from the LLM and the `data_source` (the BIP API path used) are returned as a JSON response to the client.

## Key Design Decisions & Branches Taken

-   **LLM for Path Selection**: Chosen for flexibility in understanding natural language over a rigid rule-based system for many API paths.
-   **Rule-Based Overrides**: Implemented for very common/specific queries (like "my achievements") for speed and reliability, now with fuzzy matching for typo tolerance.
-   **LLM for Query Parameterization**: Used to extract entities and keywords, allowing for more dynamic and targeted API calls.
-   **Server-Side Session for BIP Cookies**: For security and to manage BIP authentication state centrally.
-   **Data Chunking for Answering LLM**: To handle potentially large API responses and stay within LLM context limits.
-   **Answer Synthesis LLM Call**: To improve the quality of answers when data comes from multiple chunks, avoiding simple concatenation.
-   **Iterative Contextual Queries**: For complex questions like "Faculties teaching me," a multi-step process involving fetching user context first, then using that to query another API.
-   **Centralized API Registry**: To manage API definitions and descriptions, crucial for the Path Selection LLM.
-   **Generic Nova Parser with Fallbacks**: `parse_nova_api_response_data` attempts to handle common Nova structures, with the understanding that specific parsers might be needed for uniquely structured APIs in the future.
-   **Default Filters**: Applying default empty filters for certain APIs to mimic observed browser behavior and ensure correct data retrieval.
-   **Comprehensive Cookie Management**: Including `app_forward_auth` alongside other BIP cookies.

This flow allows the `mcp_server` to be a relatively intelligent intermediary between the user and the complex set of BIP APIs.
