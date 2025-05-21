/**
 * Debug Wallet - Helps diagnose wallet storage issues
 */
console.log("Loading debug wallet script");

function debugWalletStorage() {
  console.log("Starting wallet storage debug");
  
  // Check if sessionCredential exists
  const sessionCredentialElement = document.getElementById("sessionCredential");
  if (sessionCredentialElement) {
    const value = sessionCredentialElement.value;
    console.log("Session credential element found, value length:", value.length);
    console.log("First 100 characters:", value.substring(0, 100));
    
    // Try different parsing methods
    try {
      // Method 1: Direct parse
      const directParse = JSON.parse(value);
      console.log("Direct parse succeeded:", directParse);
    } catch (e) {
      console.error("Direct parse failed:", e);
    }
    
    // Method 2: Try with HTML decoding
    try {
      const decoded = value.replace(/&quot;/g, '"').replace(/&#39;/g, "'");
      const decodedParse = JSON.parse(decoded);
      console.log("HTML decoded parse succeeded:", decodedParse);
    } catch (e) {
      console.error("HTML decoded parse failed:", e);
    }
    
    // Method 3: Try handling double quotes
    if (value.startsWith('"') && value.endsWith('"')) {
      try {
        // Remove outer quotes and parse
        const innerJson = value.slice(1, -1).replace(/\\"/g, '"');
        const innerParse = JSON.parse(innerJson);
        console.log("Inner JSON parse succeeded:", innerParse);
      } catch (e) {
        console.error("Inner JSON parse failed:", e);
      }
    }
  } else {
    console.log("Session credential element not found");
  }
  
  // Check localStorage
  console.log("Checking localStorage for credentials");
  const credentials = Object.keys(localStorage).filter(key => key.startsWith('lemma_credential_'));
  console.log(`Found ${credentials.length} credentials in localStorage`);
  
  // Check for wallet
  console.log("Checking for wallet implementation");
  if (window.lemmaWallet) {
    console.log("Wallet found, checking credentials");
    window.lemmaWallet.getAllCredentials()
      .then(creds => {
        console.log(`Found ${creds.length} credentials in wallet`);
        if (creds.length > 0) {
          console.log("First credential:", creds[0]);
        }
      })
      .catch(err => console.error("Error accessing wallet credentials:", err));
  } else {
    console.log("Wallet not found or not initialized");
  }
}

// Run debug when page loads
window.addEventListener('load', function() {
  setTimeout(debugWalletStorage, 1000); // Delay to ensure elements are loaded
}); 