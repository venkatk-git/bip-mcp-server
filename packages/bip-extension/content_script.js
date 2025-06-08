// packages/bip-extension/content_script.js
// This script runs in the context of the BIP portal pages.

console.log("BIP MCP Content Script Loaded");

// Example: If you needed to get XSRF from sessionStorage
// This would require messaging back to background.js, as content scripts
// cannot make cross-origin XMLHttpRequests by default to your MCP server.

// (function() {
//   const xsrfTokenFromStorage = sessionStorage.getItem('XSRF-TOKEN');
//   if (xsrfTokenFromStorage) {
//     console.log('XSRF-TOKEN from sessionStorage:', xsrfTokenFromStorage);
//     // Send this to background.js
//     chrome.runtime.sendMessage({
//       type: "XSRF_TOKEN_FROM_STORAGE",
//       token: xsrfTokenFromStorage
//     }, response => {
//       if (chrome.runtime.lastError) {
//         console.error("Error sending XSRF from content script:", chrome.runtime.lastError.message);
//       } else {
//         console.log("Content script sent XSRF token, background responded:", response);
//       }
//     });
//   }
// })();