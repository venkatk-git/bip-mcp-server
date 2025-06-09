// packages/bip-extension/background.js

const MCP_SERVER_ENDPOINT = 'http://localhost:8000/bip/session/bip'; // Your MCP server endpoint

// Function to get a specific cookie by name for a given URL
async function getCookie(url, name) {
    try {
        const cookie = await chrome.cookies.get({ url: url, name: name });
        return cookie ? cookie.value : null;
    } catch (error) {
        console.error(`Error getting cookie "${name}":`, error);
        return null;
    }
}

// Function to send session data to MCP server
async function sendSessionDataToMCP(data) {
    try {
        const response = await fetch(MCP_SERVER_ENDPOINT, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(data),
        });
        if (!response.ok) {
            throw new Error(`MCP server responded with ${response.status}: ${await response.text()}`);
        }
        const result = await response.json();
        console.log('Successfully sent session data to MCP:', result.message);
        // Optionally, notify the user via popup or badge
        chrome.action.setBadgeText({ text: 'OK' });
        chrome.action.setBadgeBackgroundColor({ color: '#4CAF50' });

    } catch (error) {
        console.error('Error sending session data to MCP:', error);
        chrome.action.setBadgeText({ text: 'ERR' });
        chrome.action.setBadgeBackgroundColor({ color: '#F44336' });
    }
}

// Reusable function to handle tab updates and send session data
async function handleTabUpdateAndSendSession(tabId, changeInfo, tab) {
    // Check if the tab is fully loaded and the URL is the BIP portal
    // For manual sync, changeInfo might be null or different, so we primarily check tab.url
    if (tab && tab.url && tab.url.startsWith('https://bip.bitsathy.ac.in/')) {
        // For onUpdated, ensure status is complete. For manual sync, this check might not be relevant.
        if (changeInfo && changeInfo.status !== 'complete') {
            // console.log('Tab update not complete yet or not relevant for BIP session capture.');
            return;
        }
        console.log('Processing BIP Portal tab:', tab.url);

        const bipSessionCookie = await getCookie('https://bip.bitsathy.ac.in', 'bip_session');
        const xsrfTokenCookie = await getCookie('https://bip.bitsathy.ac.in', 'XSRF-TOKEN');
        const wikiUserNameCookie = await getCookie('https://bip.bitsathy.ac.in', 'wiki_wiki_UserName');
        const wikiUserIdCookie = await getCookie('https://bip.bitsathy.ac.in', 'wiki_wiki_UserID');

        if (bipSessionCookie && xsrfTokenCookie) {
            console.log('Found BIP session and XSRF token cookies.');
            const sessionData = {
                bip_session_cookie: bipSessionCookie,
                xsrf_token_cookie: xsrfTokenCookie,
                wiki_user_name_cookie: wikiUserNameCookie,
                wiki_user_id_cookie: wikiUserIdCookie,
            };
            console.log('Session Data:', sessionData);
            await sendSessionDataToMCP(sessionData);
        } else {
            console.log('Required BIP cookies not found. User might not be logged in or cookies are not yet set.');
            chrome.action.setBadgeText({ text: '' });
        }
    }
}

// Listener for when a tab is updated
chrome.tabs.onUpdated.addListener(handleTabUpdateAndSendSession);

// Listener for messages from popup.js or content_script.js
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.type === "MANUAL_SYNC_REQUEST") {
        console.log("Manual sync request received from popup.");
        (async () => {
            try {
                const [currentTab] = await chrome.tabs.query({ active: true, currentWindow: true });
                if (currentTab) {
                    // Call the handler. Pass null for changeInfo as it's a manual trigger.
                    await handleTabUpdateAndSendSession(currentTab.id, null, currentTab);
                    sendResponse({ status: "Sync initiated from background." });
                } else {
                    console.error("No active tab found for manual sync.");
                    sendResponse({ status: "Error: No active tab found." });
                }
            } catch (error) {
                console.error("Error during manual sync:", error);
                sendResponse({ status: `Error: ${error.message}` });
            }
        })();
        return true; // Indicates you wish to send a response asynchronously
    }
    // Add other message handlers here if needed (e.g., for XSRF_TOKEN_FROM_STORAGE)
});


// Optional: Listen for clicks on the extension icon (if you have a popup.html)
// This now primarily opens the popup. The popup handles manual sync.
chrome.action.onClicked.addListener((tab) => {
    console.log("Extension icon clicked. Popup should open.");
    // Default behavior is to open popup.html if defined in manifest.
    // If you need to do something else before popup opens, or instead of it, do it here.
});

console.log('BIP Session Helper background script loaded. Manual sync enabled.');
