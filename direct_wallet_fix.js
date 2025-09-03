// Direct Wallet Fix - Run this in the browser console on lemma.id/wallet
// This will immediately fix the credential display issue

console.log('🔧 DIRECT WALLET FIX - Running...');

// Step 1: Check current wallet status
if (typeof lemmaWallet !== 'undefined' && lemmaWallet) {
    console.log('✅ Found existing wallet instance');
    console.log(`📊 Current memory cache: ${lemmaWallet.memoryCache.size} credentials`);
    
    // List current credentials
    for (const [id, cred] of lemmaWallet.memoryCache) {
        console.log(`  - ${cred.packageType}: ${id} (${cred.claims?.email || 'no email'})`);
    }
} else {
    console.log('❌ No wallet instance found');
}

// Step 2: Check localStorage for transferred credentials
console.log('\n🔍 Checking localStorage...');
const storedCredentials = localStorage.getItem('lemma_credentials');
if (storedCredentials) {
    try {
        const parsed = JSON.parse(storedCredentials);
        console.log(`📊 localStorage has ${parsed.length} credentials:`);
        parsed.forEach((cred, i) => {
            console.log(`  ${i + 1}. ${cred.packageType}: ${cred.id}`);
            if (cred.claims?.email) {
                console.log(`     Email: ${cred.claims.email}`);
            }
            if (cred.claims?.permissionId) {
                console.log(`     Permission: ${cred.claims.permissionId}`);
            }
            if (cred.claims?.isHuman) {
                console.log(`     Is Human: ${cred.claims.isHuman}`);
            }
        });
    } catch (e) {
        console.log('❌ localStorage data corrupted');
    }
} else {
    console.log('❌ No localStorage data found');
}

// Step 3: Force reload the wallet with all credentials
console.log('\n🔄 Force reloading wallet with all credentials...');

async function forceFixWallet() {
    try {
        // Get stored credentials
        const storedCredentials = localStorage.getItem('lemma_credentials');
        if (!storedCredentials) {
            console.log('❌ No stored credentials to reload');
            return;
        }
        
        const credentials = JSON.parse(storedCredentials);
        console.log(`📊 Reloading ${credentials.length} stored credentials`);
        
        // Reinitialize wallet if it exists
        if (typeof lemmaWallet !== 'undefined' && lemmaWallet) {
            // Clear current wallet
            lemmaWallet.memoryCache.clear();
            
            // Reload each credential
            for (const cred of credentials) {
                lemmaWallet.memoryCache.set(cred.id, cred);
                console.log(`✅ Reloaded: ${cred.packageType} - ${cred.id}`);
            }
            
            console.log(`✅ Wallet reloaded with ${lemmaWallet.memoryCache.size} credentials`);
            
            // Force display update
            if (typeof loadWalletData === 'function') {
                console.log('🔄 Refreshing display...');
                await loadWalletData();
                console.log('✅ Display refreshed');
            } else {
                console.log('⚠️ loadWalletData function not found - manually refresh page');
            }
            
            // Test credential retrieval
            const identityCredentials = await lemmaWallet.getCredentials('identity');
            const permissionCredentials = await lemmaWallet.getCredentials('permission');
            
            console.log('\n📊 Final test:');
            console.log(`  Identity (PoH) credentials: ${identityCredentials.length}`);
            console.log(`  Permission credentials: ${permissionCredentials.length}`);
            
            if (identityCredentials.length > 0 && permissionCredentials.length > 0) {
                console.log('🎯 SUCCESS: Both types available - wallet page should show both sections!');
            } else if (identityCredentials.length > 0) {
                console.log('⚠️ Only PoH lemmas available');
            } else if (permissionCredentials.length > 0) {
                console.log('⚠️ Only permission lemmas available');
            } else {
                console.log('❌ No credentials available');
            }
            
        } else {
            console.log('❌ No wallet instance to reload');
        }
        
    } catch (error) {
        console.log(`❌ Force fix failed: ${error.message}`);
    }
}

// Step 4: Add refresh buttons directly to the page if they don't exist
console.log('\n🔧 Adding refresh buttons to page...');

function addRefreshButtons() {
    // Find the credential management section
    const credentialSection = document.querySelector('.credential-management');
    if (credentialSection) {
        // Check if buttons already exist
        const existingButtons = credentialSection.querySelector('.force-refresh-buttons');
        if (existingButtons) {
            console.log('⚠️ Refresh buttons already exist');
            return;
        }
        
        // Create button container
        const buttonContainer = document.createElement('div');
        buttonContainer.className = 'force-refresh-buttons';
        buttonContainer.style.cssText = 'margin: 10px 0; text-align: center; padding: 10px; background: #f8f9fa; border-radius: 6px;';
        
        // Create buttons
        buttonContainer.innerHTML = `
            <button onclick="forceFixWallet()" style="background: #dc3545; color: white; border: none; padding: 8px 16px; border-radius: 4px; margin: 0 5px; cursor: pointer;">
                🔧 Force Fix Wallet
            </button>
            <button onclick="location.reload(true)" style="background: #007bff; color: white; border: none; padding: 8px 16px; border-radius: 4px; margin: 0 5px; cursor: pointer;">
                🔄 Hard Refresh Page
            </button>
            <button onclick="console.clear(); forceFixWallet()" style="background: #28a745; color: white; border: none; padding: 8px 16px; border-radius: 4px; margin: 0 5px; cursor: pointer;">
                🚀 Debug & Fix
            </button>
        `;
        
        // Insert at the top of the credential section
        credentialSection.insertBefore(buttonContainer, credentialSection.firstChild);
        console.log('✅ Added refresh buttons to wallet page');
    } else {
        console.log('❌ Could not find credential section to add buttons');
    }
}

// Add the buttons
addRefreshButtons();

// Make the fix function globally available
window.forceFixWallet = forceFixWallet;

// Step 5: Run the fix automatically
console.log('\n🚀 Running automatic fix...');
forceFixWallet();

console.log('\n📋 INSTRUCTIONS:');
console.log('1. Check the console output above for the fix results');
console.log('2. If successful, both PoH and permission sections should now be visible');
console.log('3. If not, click the "🔧 Force Fix Wallet" button that was added to the page');
console.log('4. Or click "🔄 Hard Refresh Page" to reload everything');
