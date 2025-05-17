// lemma-plan.js - Displays the Lemma Network content

document.addEventListener('DOMContentLoaded', function() {
    // Initialize variables
    let currentPage = 0;
    const totalPages = 5;
    
    // Content for each "page" of the plan
    const planContent = [
        // Page 1: Overview and Architecture
        {
            title: "Lemma - Decentralized Identity Architecture",
            sections: [
                {
                    heading: "Core Architecture",
                    content: `
                        <p>Lemma provides a secure, modular architecture for verifying humans with minimal data collection 
                        and strong cryptographic standards. The system is designed around the following principles:</p>
                        <ul>
                            <li><strong>Privacy is paramount</strong>: We collect only what's necessary to verify humanness</li>
                            <li><strong>Self-sovereignty is essential</strong>: Users control their own identity and what they share</li>
                            <li><strong>Decentralization reduces risk</strong>: No single point of failure in the verification system</li>
                            <li><strong>Cryptographic trust</strong>: Using Ed25519 signatures and DIDs for security</li>
                        </ul>
                    `
                },
                {
                    heading: "Technical Components",
                    content: `
                        <p>The Lemma system consists of the following core components:</p>
                        <ul>
                            <li><strong>Credential Service</strong>: Issues and verifies W3C Verifiable Credentials</li>
                            <li><strong>DID Resolver</strong>: Multi-method resolver supporting did:key, did:web, did:ethr, and did:lemma</li>
                            <li><strong>Lemma Wallet</strong>: Client-side storage and management of credentials</li>
                            <li><strong>Verification API</strong>: Endpoints for verifying presented credentials</li>
                            <li><strong>Zero-Knowledge Proofs</strong>: Selective disclosure of credential attributes</li>
                        </ul>
                    `
                }
            ]
        },
        
        // Page 2: Verification Flow
        {
            title: "Verification Workflows",
            sections: [
                {
                    heading: "Identity Verification to Credential Issuance",
                    content: `
                        <p>The verification process follows these steps:</p>
                        <ol>
                            <li>User initiates verification via "Verify Lemma" button</li>
                            <li>Lemma creates a verification session (optionally with Stripe Identity)</li>
                            <li>User completes identity verification</li>
                            <li>Upon successful verification, a Verifiable Credential is issued</li>
                            <li>Credential is stored in the Lemma wallet (browser-based)</li>
                            <li>User is redirected to protected page with their credential</li>
                        </ol>
                        <p>This secure workflow ensures only real humans receive credentials while collecting minimal personal data.</p>
                    `
                },
                {
                    heading: "Credential Presentation and Verification",
                    content: `
                        <p>For sites integrating with Lemma, this workflow enables verification:</p>
                        <ol>
                            <li>User visits a site in the Lemma network</li>
                            <li>Site generates a cryptographic challenge</li>
                            <li>Lemma wallet creates a Verifiable Presentation containing the credential</li>
                            <li>Site verifies the presentation cryptographically</li>
                            <li>If verification succeeds, the site grants access to protected content</li>
                        </ol>
                        <p>This enables a "verify once, use anywhere" model across the Lemma network.</p>
                    `
                }
            ]
        },
        
        // Page 3: Security Features
        {
            title: "Security Features",
            sections: [
                {
                    heading: "Cryptographic Foundations",
                    content: `
                        <p>Lemma's security is built on strong cryptographic principles:</p>
                        <ul>
                            <li><strong>Ed25519 Signatures</strong>: Fast, secure digital signatures for credential issuance</li>
                            <li><strong>Challenge-Response Protocol</strong>: Prevents replay attacks during verification</li>
                            <li><strong>Decentralized Identifiers (DIDs)</strong>: Supporting multiple methods for interoperability</li>
                            <li><strong>Hardware-Backed Security</strong>: Support for TPM, Secure Enclave, and Android Keystore</li>
                        </ul>
                    `
                },
                {
                    heading: "Privacy Protections",
                    content: `
                        <p>Privacy is embedded throughout the system:</p>
                        <ul>
                            <li><strong>Zero-Knowledge Proofs</strong>: Reveal only necessary attributes (e.g., isHuman=true)</li>
                            <li><strong>Client-Side Storage</strong>: Credentials stored in the user's browser, not centrally</li>
                            <li><strong>Selective Disclosure</strong>: Fine-grained control over what information is shared</li>
                            <li><strong>Minimal Data Collection</strong>: Only verifies humanity, collects no personal information</li>
                            <li><strong>P2P Revocation</strong>: Decentralized credential revocation system</li>
                        </ul>
                    `
                }
            ]
        },
        
        // Page 4: Wallet Architecture
        {
            title: "Lemma Wallet Architecture",
            sections: [
                {
                    heading: "Client-Side Wallet",
                    content: `
                        <p>The Lemma wallet provides credential management directly in the browser:</p>
                        <ul>
                            <li><strong>IndexedDB Storage</strong>: Secure, persistent storage across browser sessions</li>
                            <li><strong>Automatic Detection</strong>: Wallet automatically initializes on Lemma-integrated pages</li>
                            <li><strong>Portability</strong>: Import/export functionality for cross-device usage</li>
                            <li><strong>Credential Management</strong>: View, delete, and present credentials as needed</li>
                        </ul>
                    `
                },
                {
                    heading: "Cross-Page Communication",
                    content: `
                        <p>The wallet enables seamless verification across pages:</p>
                        <ul>
                            <li><strong>Automatic Presentation</strong>: Creates presentations in response to challenges</li>
                            <li><strong>Secure API</strong>: JavaScript API for sites to request verification</li>
                            <li><strong>Persistence</strong>: Maintains sessions across pages and sites</li>
                            <li><strong>Encryption</strong>: End-to-end encryption of credentials in storage and transit</li>
                        </ul>
                    `
                }
            ]
        },
        
        // Page 5: Implementation Roadmap
        {
            title: "Implementation Roadmap",
            sections: [
                {
                    heading: "Current Implementation",
                    content: `
                        <p>The current system supports:</p>
                        <ul>
                            <li><strong>Browser LocalStorage</strong>: Basic credential storage in browser</li>
                            <li><strong>JSON Backup/Restore</strong>: Manual export/import of credentials</li>
                            <li><strong>W3C Verifiable Credentials</strong>: Standard-compliant credentials</li>
                            <li><strong>Basic Lemma Wallet</strong>: Core wallet functionality with integrated UI</li>
                        </ul>
                    `
                },
                {
                    heading: "Future Enhancements",
                    content: `
                        <p>Planned improvements include:</p>
                        <ul>
                            <li><strong>Mobile Wallet Integration</strong>: Native apps for iOS and Android</li>
                            <li><strong>Hardware Security</strong>: Enhanced TPM and secure enclave support</li>
                            <li><strong>Decentralized Storage</strong>: Optional storage on IPFS or similar networks</li>
                            <li><strong>Enhanced ZKPs</strong>: More advanced zero-knowledge proof capabilities</li>
                            <li><strong>Third-Party Wallet Support</strong>: Integration with existing wallets</li>
                            <li><strong>Expanded DID Support</strong>: Additional DID methods and resolution</li>
                        </ul>
                    `
                }
            ]
        }
    ];
    
    // Function to render the current page
    function renderCurrentPage() {
        const pageData = planContent[currentPage];
        const planContainer = document.getElementById('lemma-plan-container');
        
        // Clear previous content
        planContainer.innerHTML = '';
        
        // Create title element
        const titleElement = document.createElement('h2');
        titleElement.className = 'plan-title';
        titleElement.textContent = pageData.title;
        planContainer.appendChild(titleElement);
        
        // Create content for each section
        pageData.sections.forEach(section => {
            // Section heading
            const headingElement = document.createElement('h3');
            headingElement.className = 'plan-section-heading';
            headingElement.textContent = section.heading;
            planContainer.appendChild(headingElement);
            
            // Section content
            const contentDiv = document.createElement('div');
            contentDiv.className = 'plan-section-content';
            contentDiv.innerHTML = section.content;
            planContainer.appendChild(contentDiv);
        });
        
        // Update pagination indicators
        updatePagination();
    }
    
    // Function to update pagination controls
    function updatePagination() {
        const paginationElement = document.getElementById('lemma-plan-pagination');
        paginationElement.innerHTML = '';
        
        // Previous button
        const prevButton = document.createElement('button');
        prevButton.className = 'pagination-button';
        prevButton.textContent = '← Previous';
        prevButton.disabled = currentPage === 0;
        prevButton.addEventListener('click', () => {
            if (currentPage > 0) {
                currentPage--;
                renderCurrentPage();
            }
        });
        paginationElement.appendChild(prevButton);
        
        // Page indicator
        const pageIndicator = document.createElement('span');
        pageIndicator.className = 'page-indicator';
        pageIndicator.textContent = `Page ${currentPage + 1} of ${totalPages}`;
        paginationElement.appendChild(pageIndicator);
        
        // Next button
        const nextButton = document.createElement('button');
        nextButton.className = 'pagination-button';
        nextButton.textContent = 'Next →';
        nextButton.disabled = currentPage === totalPages - 1;
        nextButton.addEventListener('click', () => {
            if (currentPage < totalPages - 1) {
                currentPage++;
                renderCurrentPage();
            }
        });
        paginationElement.appendChild(nextButton);
    }
    
    // Initialize the plan view if the container exists
    const planContainer = document.getElementById('lemma-plan-container');
    if (planContainer) {
        renderCurrentPage();
    }
}); 