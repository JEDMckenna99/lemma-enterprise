workspace {
    model {
        user = person "User" "A user with a Lemma wallet"
        
        lemmaSystem = softwareSystem "Lemma Platform" {
            wallet = container "User Wallet" "IndexedDB" "Browser Storage" {
                tags "Client"
            }
            bridge = container "Wallet Bridge" "Cross-origin SSO" "HTML/JS" {
                tags "Client"
            }
            backend = container "Lemma Backend" "Flask API" "Python" {
                tags "Server"
            }
            postgres = container "PostgreSQL" "Persistent Storage" "Database" {
                tags "Storage"
            }
            redis = container "Redis" "Session Storage" "Cache" {
                tags "Storage"
            }
        }
        
        thirdPartySite = softwareSystem "Third-Party Site" "Customer site using Lemma SDK" {
            tags "External"
        }
        
        # Relationships
        user -> wallet "Unlocks via passkey"
        wallet -> backend "Passkey auth"
        thirdPartySite -> bridge "Loads iframe"
        bridge -> wallet "Reads session"
        wallet -> backend "Syncs revocation bloom"
        backend -> postgres "Reads/writes"
        backend -> redis "Session storage"
    }
    
    views {
        systemContext lemmaSystem {
            include *
            autolayout lr
        }
        container lemmaSystem {
            include *
            autolayout lr
        }
    }
}