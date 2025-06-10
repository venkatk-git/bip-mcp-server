# BIP MCP Server Project

This project integrates with the BIT Information Portal (BIP) to provide an AI-powered assistant capable of answering natural language questions about BIP data. It consists of a Model Context Protocol (MCP) server, a Chrome browser extension for session management, and a placeholder for a web application frontend.

## Project Structure

The project is organized as a monorepo with the following main components:

-   **`packages/mcp_server/`**: The core FastAPI-based MCP server. This server interacts with BIP APIs and uses Language Models (LLMs) to process user queries.
-   **`packages/bip-extension/`**: A Chrome browser extension used to capture active BIP session cookies and securely transmit them to the MCP server.
-   **`apps/web/`**: A React/Vite frontend application (currently a placeholder, intended for user interaction with the assistant).
-   **`apps/api/`**: A placeholder for a potential future standalone API related to this project.
-   **`memory_bank`**: A conceptual file for storing long-term project context, guidelines, and architectural decisions.

## Features

### 1. MCP Server (`packages/mcp_server`)

-   **FastAPI Framework**: Built using the modern, high-performance FastAPI framework.
-   **BIP Integration**: Securely connects to the live BIP portal by leveraging session cookies obtained via the Chrome extension.
-   **AI-Powered Assistant (`/assistant/ask` endpoint)**:
    -   **Natural Language Understanding**: Accepts user questions in natural language.
    -   **Intelligent API Routing**: Uses an LLM (Google Gemini) to determine the most relevant BIP API endpoint to query based on the user's question. Currently supports:
        -   `/nova-api/students` (Student profiles)
        -   `/nova-api/departments` (Department listings)
        -   `/nova-api/academic-feedbacks` (Academic feedback for the user)
        -   `/nova-api/student-activity-masters` (Master list of college events/activities)
        -   `/nova-api/student-achievement-loggers` (Logged-in student's personal achievements/participations)
        -   `/nova-api/academic-course-faculty-mappings` (Faculty assignments to courses)
    -   **Contextual Query Parameterization**: Employs an LLM to extract entities (like student names, event names, department names, locations, keywords) from the user's question. These are used to construct targeted API calls with `search` and `filters` parameters.
    -   **Optimized Data Fetching**:
        -   For specific entity queries, fetches minimal data.
        -   For broader list queries, uses pagination (`perPage=150`) and fetches multiple pages as needed (up to a safety limit).
    -   **Data Parsing & Normalization**: Parses complex JSON responses from BIP APIs into a more uniform format.
    -   **LLM-Generated Answers**: Uses an LLM to synthesize a natural language answer based on the retrieved data.
        -   **Chunking**: Handles large datasets by splitting them into smaller chunks for the LLM to process, respecting token limits.
        -   **Early Exit**: For specific entity queries, if an answer is found in an early chunk, further processing is stopped to improve efficiency.
        -   **Tone Customization**: Prompts are designed to give the assistant a helpful, slightly witty, and human-like tone.
    -   **Typo Tolerance**: The query understanding LLM has some built-in tolerance for minor typos in user questions.
    -   **User-Contextual Queries**: Can handle queries like "Faculties teaching me" by first fetching the logged-in student's details (department, semester) and then using that context to query for relevant course-faculty mappings.
-   **Session Management**:
    -   Receives BIP session cookies (`bip_session`, `XSRF-TOKEN`, `wiki_wiki_UserID`, `wiki_wiki_UserName`) from the Chrome extension via a dedicated endpoint (`/bip/session/bip`).
    -   Stores these cookies securely in the server-side session (using `starlette.middleware.sessions`).
    -   Uses these stored cookies for all subsequent authenticated requests to BIP.
-   **Caching**: Implements caching for department data to reduce redundant API calls.
-   **Configuration**: Uses a `.env` file for managing sensitive information like `GOOGLE_API_KEY`.

### 2. BIP Chrome Extension (`packages/bip-extension`)

-   **Purpose**: To securely capture the necessary session cookies from an active BIP session in the user's browser.
-   **Functionality**:
    -   A popup UI allows the user to trigger the cookie capture.
    -   A background script reads cookies for the `bip.bitsathy.ac.in` domain.
    -   Sends the captured cookies to the MCP server's `/bip/session/bip` endpoint.

### 3. Web Application (`apps/web`)

-   **Technology**: Built with React and Vite.
-   **Purpose**: Intended as the primary user interface for interacting with the AI assistant.
-   **Current Status**: Basic Vite/React boilerplate. Integration with the MCP server's `/assistant/ask` endpoint is a future task.

## Setup and Running

### Prerequisites

-   Python 3.10+
-   Node.js and npm (for the web app, if developing it)
-   Access to Google Gemini API (requires a `GOOGLE_API_KEY`)
-   An active account and session on the BIP portal.

### 1. MCP Server (`packages/mcp_server`)

1.  **Navigate to the project root directory (e.g., `bip-mcp-server`):**
    Ensure your terminal is in the main project directory, not inside `packages/mcp_server`.
2.  **Create and activate a virtual environment (preferably in the project root or `packages/mcp_server`):**
    If creating in `packages/mcp_server`:
    ```bash
    cd packages/mcp_server
    python -m venv .venv
    source .venv/bin/activate  # On Windows: .venv\Scripts\activate
    cd ../.. # Go back to project root
    ```
    If creating in project root:
    ```bash
    python -m venv .venv 
    source .venv/bin/activate # On Windows: .venv\Scripts\activate
    ```
3.  **Install Python dependencies (ensure your virtual environment is active):**
    ```bash
    pip install -r packages/mcp_server/requirements.txt
    ```
4.  **Configure Environment Variables:**
    Create a `.env` file in the `packages/mcp_server` directory (i.e., `packages/mcp_server/.env`) with your Google API key:
    ```env
    GOOGLE_API_KEY="YOUR_GOOGLE_API_KEY_HERE"
    # Optional: Define a custom MCP_SERVER_SESSION_SECRET_KEY for Starlette sessions
    # MCP_SERVER_SESSION_SECRET_KEY="your_strong_random_secret_key"
    ```
5.  **Run the MCP server (from the project root directory):**
    ```bash
    uvicorn packages.mcp_server.main:app --reload --port 8000
    ```
    The server will be available at `http://localhost:8000`. The API documentation (Swagger UI) will be at `http://localhost:8000/docs`.

### 2. BIP Chrome Extension (`packages/bip-extension`)

1.  Open Google Chrome and navigate to `chrome://extensions`.
2.  Enable "Developer mode" (usually a toggle in the top right).
3.  Click "Load unpacked".
4.  Select the `packages/bip-extension` directory from this project.
5.  The extension icon should appear in your Chrome toolbar.

### 3. Using the System

1.  Log in to the BIP portal (`https://bip.bitsathy.ac.in`) in your Chrome browser.
2.  Click the "BIP Session Sync" Chrome extension icon.
3.  Click the "Sync BIP Session with MCP Server" button in the extension popup. This will send your BIP cookies to the MCP server running on `http://localhost:8000`.
4.  You can now send queries to the MCP server's `/assistant/ask` endpoint (e.g., using Postman, curl, or eventually the web app).

    **Example `curl` for `/assistant/ask`:**
    ```bash
    curl -X POST http://localhost:8000/assistant/ask \
    -H "Content-Type: application/json" \
    -b "mcp_server_session=YOUR_MCP_SERVER_SESSION_COOKIE_FROM_BROWSER_DEVTOOLS_AFTER_SYNC" \
    -d '{
        "user_question": "Who teaches Business Analytics and Intelligence?",
        "item_id": null
    }'
    ```
    *(Note: The `mcp_server_session` cookie is set by the MCP server itself after the initial sync. You'd typically grab this from your browser's developer tools after the first interaction with the server that sets a session, or rely on your HTTP client to manage cookies.)*

### 4. Web Application (`apps/web`) (Optional Development)

1.  **Navigate to the web app directory:**
    ```bash
    cd apps/web
    ```
2.  **Install Node.js dependencies:**
    ```bash
    npm install
    ```
3.  **Run the development server:**
    ```bash
    npm run dev
    ```

## Key Technologies

-   **Backend (MCP Server)**: Python, FastAPI, Uvicorn, HTTPX, Pydantic
-   **AI/LLM**: Google Gemini API
-   **Browser Extension**: JavaScript, HTML, CSS (standard Chrome extension technologies)
-   **Frontend (Web App)**: React, Vite, TypeScript (currently placeholder)
-   **Monorepo Management**: Implicit (manual directory structure)

## Future Enhancements / Areas to Work On

-   **Refine LLM Prompts**: Continuously improve prompts for path selection, query understanding, and answer generation for better accuracy and tone.
-   **Advanced Iterative Reasoning**: Implement more complex multi-step reasoning for queries that require sequential information gathering (e.g., "Faculties teaching my specific elective course this semester").
-   **Error Handling & Robustness**: Enhance error handling for API failures, unexpected data structures, and LLM issues.
-   **Filter Construction**: Develop more sophisticated logic to construct precise `filters` parameters for BIP APIs based on extracted query details, rather than relying solely on the `search` parameter for some cases.
-   **Web Application Development**: Fully develop the `apps/web` frontend to provide a user-friendly interface for the assistant.
-   **Security**: Review and enhance security aspects, especially around session management and API key handling.
-   **Testing**: Add comprehensive unit and integration tests.
-   **Memory Bank Integration**: Develop a system to utilize the `memory_bank` for persistent project context.
-   **Configuration Management**: Potentially move more configurations (e.g., API paths, default parameters) to a more structured config system if needed.
