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

// Listener for when a tab is updated (e.g., after login or navigation)
chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
    // Check if the tab is fully loaded and the URL is the BIP portal
    if (changeInfo.status === 'complete' && tab.url && tab.url.startsWith('https://bip.bitsathy.ac.in/')) {
        console.log('BIP Portal tab updated:', tab.url);

        // Attempt to retrieve cookies.
        // This is a naive check; ideally, you'd detect a successful login more robustly.
        // For example, by checking if the URL is a known post-login page.
        const bipSessionCookie = await getCookie('https://bip.bitsathy.ac.in', 'bip_session');
        const xsrfTokenCookie = await getCookie('https://bip.bitsathy.ac.in', 'XSRF-TOKEN');
        // You mentioned XSRF-TOKEN was also in sessionStorage. If the cookie isn't reliable,
        // you might need the content script to fetch it and message it to background.js.
        // For now, let's assume the XSRF-TOKEN cookie is present and usable.

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
            await sendSessionDataToMCP(sessionData);
        } else {
            console.log('Required BIP cookies not found. User might not be logged in or cookies are not yet set.');
            // Clear badge if cookies are not found after a page load
            chrome.action.setBadgeText({ text: '' });
        }
    }
});

// Optional: Listen for clicks on the extension icon (if you have a popup.html)
chrome.action.onClicked.addListener((tab) => {
    // Example: open a popup or trigger a manual sync
    console.log("Extension icon clicked for tab:", tab.url);
    // If you want to manually trigger the cookie check and send:
    if (tab.url && tab.url.startsWith('https://bip.bitsathy.ac.in/')) {
        chrome.tabs.onUpdated.call(this, tab.id, { status: 'complete' }, tab); // Re-run the logic
    }
});

console.log('BIP Session Helper background script loaded.');