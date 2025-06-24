# Lemma Diagrams

This folder contains technical diagrams and visual documentation for the Lemma Enterprise Digital Verification Platform.

## Available Diagrams

### 🔄 [Bot Shield Circuit](./bot-shield-circuit.md)
**The complete Lemma verification flow diagram**
- Shows the three core flows: Check, Shield, and Revocation
- Illustrates user visible vs background operations
- Documents the continuous protection loop across websites
- Demonstrates offline-first architecture with smart fallbacks

### 🌐 [API Endpoints](./api-endpoints.md)
**Complete API architecture documentation**
- All Shield API endpoints and their relationships
- Request/response flow diagrams
- Integration patterns and examples

### 🏗️ [Site Structure](./site-structure.md)
**Website and application architecture**
- Component relationships and data flow
- Integration points and dependencies
- Deployment architecture diagrams

## Diagram Usage

### In Documentation
All diagrams are referenced throughout the Lemma documentation:
- **README.md** - Overview and quick start
- **LEMMA_WHITEPAPER.md** - Technical deep dive
- **Integration guides** - Implementation details

### In Presentations
These diagrams are designed for:
- Technical presentations to developers
- Business presentations to stakeholders
- Security audits and compliance reviews
- Investor presentations and demos

### For Development
Developers can use these diagrams to:
- Understand system architecture before integration
- Debug flow issues and edge cases
- Design new features and extensions
- Optimize performance and user experience

## Diagram Standards

### Visual Style
- **Mermaid format** for version control and collaboration
- **Color coding** for different system layers
- **Clear labeling** of all flow conditions and outcomes
- **Responsive design** for mobile and desktop viewing

### Content Standards
- **User-centric perspective** showing what users see vs background operations
- **Performance metrics** included where relevant
- **Security considerations** highlighted throughout
- **Business value** clearly articulated

### Update Process
1. **Source diagrams** are maintained in this folder
2. **Referenced copies** are embedded in relevant documentation
3. **Version control** tracks all changes for audit purposes
4. **Regular reviews** ensure accuracy with implementation

## Contributing

When updating diagrams:
1. **Edit source files** in this folder first
2. **Update references** in documentation that embeds the diagram
3. **Test rendering** in multiple contexts (GitHub, documentation sites)
4. **Validate accuracy** against current implementation

For questions about diagrams or requests for new visualizations, please see the main project documentation or contact the development team. 