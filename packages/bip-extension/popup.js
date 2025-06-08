// packages/bip-extension/popup.js
document.addEventListener('DOMContentLoaded', function () {
    const statusEl = document.getElementById('status');
    const syncButton = document.getElementById('syncButton');

    // You can use chrome.storage.local to store status from background.js
    // Or query the background script for current status.
    // For simplicity, this popup doesn't show live status yet.
    statusEl.textContent = "Ready. Logs in Console.";

    syncButton.addEventListener('click', async () => {
        statusEl.textContent = "Attempting sync...";
        try {
            // Get current active tab
            const [currentTab] = await chrome.tabs.query({ active: true, currentWindow: true });
            if (currentTab && currentTab.url && currentTab.url.startsWith('https://bip.bitsathy.ac.in/')) {
                // Trigger the logic in background.js as if the tab just updated
                // This is a bit of a hacky way to re-trigger; better would be direct messaging
                // to background script to perform the check.
                await chrome.runtime.sendMessage({ type: "MANUAL_SYNC_REQUEST" }); // Background would need to listen for this
                statusEl.textContent = "Sync triggered. Check console & badge.";
            } else {
                statusEl.textContent = "Not on BIP portal.";
            }
        } catch (e) {
            statusEl.textContent = "Error triggering sync.";
            console.error(e);
        }
    });
});

// In background.js, you would add:
// chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
//   if (message.type === "MANUAL_SYNC_REQUEST") {
//     console.log("Manual sync request received");
//     // Re-run your cookie fetching and sending logic here
//     // For example, by calling a common function that onUpdated also calls.
//     // This requires refactoring onUpdated a bit.
//     (async () => {
//       const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
//       if (tab) { // Call the main logic handler
//         await handleTabUpdate(tab.id, { status: 'complete' }, tab);
//       }
//     })();
//     sendResponse({status: "Sync initiated"});
//     return true; // Indicates you wish to send a response asynchronously
//   }
// });
// async function handleTabUpdate(tabId, changeInfo, tab) { ... your existing onUpdated logic ... }
// And change chrome.tabs.onUpdated to call `handleTabUpdate`.