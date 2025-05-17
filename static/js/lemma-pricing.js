// lemma-pricing.js - Displays the Lemma pricing model with interactive visualization

document.addEventListener('DOMContentLoaded', function() {
    // Initialize pricing parameters
    const initialFee = 0.50; // Base monthly fee per user (p₀)
    const halfingPoints = 10; // Number of sites (M) at which price halves
    const alpha = Math.log(2) / halfingPoints; // Decay constant
    
    // Function to calculate price based on number of sites
    function calculatePrice(basePrice, numSites) {
        return basePrice * Math.exp(-alpha * numSites);
    }
    
    // Function to draw the pricing curve graph
    function drawPricingGraph() {
        const canvas = document.getElementById('pricing-curve');
        if (!canvas) return;
        
        const ctx = canvas.getContext('2d');
        const width = canvas.width;
        const height = canvas.height;
        
        // Clear canvas
        ctx.clearRect(0, 0, width, height);
        
        // Set up graph parameters
        const maxSites = 30; // X-axis maximum
        const padding = 40; // Padding from edges
        const graphWidth = width - 2 * padding;
        const graphHeight = height - 2 * padding;
        
        // Draw axes
        ctx.beginPath();
        ctx.strokeStyle = '#333';
        ctx.lineWidth = 2;
        
        // X axis
        ctx.moveTo(padding, height - padding);
        ctx.lineTo(width - padding, height - padding);
        
        // Y axis
        ctx.moveTo(padding, height - padding);
        ctx.lineTo(padding, padding);
        ctx.stroke();
        
        // Draw X axis labels
        ctx.fillStyle = '#333';
        ctx.font = '12px Arial';
        ctx.textAlign = 'center';
        
        // X axis title
        ctx.fillText('Number of Integrated Sites (N)', width / 2, height - 10);
        
        // X axis ticks
        for (let i = 0; i <= maxSites; i += 5) {
            const x = padding + (i / maxSites) * graphWidth;
            ctx.beginPath();
            ctx.moveTo(x, height - padding);
            ctx.lineTo(x, height - padding + 5);
            ctx.stroke();
            ctx.fillText(i, x, height - padding + 20);
        }
        
        // Draw Y axis labels
        ctx.textAlign = 'right';
        ctx.textBaseline = 'middle';
        
        // Y axis title
        ctx.save();
        ctx.translate(10, height / 2);
        ctx.rotate(-Math.PI / 2);
        ctx.fillText('Monthly Fee per User ($)', 0, 0);
        ctx.restore();
        
        // Y axis ticks
        for (let i = 0; i <= 5; i++) {
            const value = initialFee * (i / 5);
            const y = height - padding - (i / 5) * graphHeight;
            ctx.beginPath();
            ctx.moveTo(padding, y);
            ctx.lineTo(padding - 5, y);
            ctx.stroke();
            ctx.fillText(value.toFixed(2), padding - 10, y);
        }
        
        // Draw the curve
        ctx.beginPath();
        ctx.strokeStyle = '#6B3FA0'; // Lemma primary color
        ctx.lineWidth = 3;
        
        for (let x = 0; x <= maxSites; x += 0.5) {
            const price = calculatePrice(initialFee, x);
            const normalizedPrice = price / initialFee; // Normalize to 0-1 range
            
            const canvasX = padding + (x / maxSites) * graphWidth;
            const canvasY = height - padding - normalizedPrice * graphHeight;
            
            if (x === 0) {
                ctx.moveTo(canvasX, canvasY);
            } else {
                ctx.lineTo(canvasX, canvasY);
            }
        }
        ctx.stroke();
        
        // Highlight key points
        const keyPoints = [
            { sites: 0, label: `$${initialFee.toFixed(2)}` },
            { sites: 5, label: `$${calculatePrice(initialFee, 5).toFixed(2)}` },
            { sites: 10, label: `$${calculatePrice(initialFee, 10).toFixed(2)}` },
            { sites: 20, label: `$${calculatePrice(initialFee, 20).toFixed(2)}` }
        ];
        
        keyPoints.forEach(point => {
            const price = calculatePrice(initialFee, point.sites);
            const normalizedPrice = price / initialFee;
            
            const x = padding + (point.sites / maxSites) * graphWidth;
            const y = height - padding - normalizedPrice * graphHeight;
            
            // Draw point
            ctx.beginPath();
            ctx.fillStyle = '#4A2C71';
            ctx.arc(x, y, 5, 0, Math.PI * 2);
            ctx.fill();
            
            // Draw label
            ctx.fillStyle = '#000';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'bottom';
            ctx.fillText(point.label, x, y - 10);
        });
    }
    
    // Function to update pricing calculator
    function updateCalculator() {
        const numSites = parseInt(document.getElementById('num-sites').value) || 1;
        const numUsers = parseInt(document.getElementById('num-users').value) || 100;
        
        const perUserPrice = calculatePrice(initialFee, numSites);
        const monthlyTotal = perUserPrice * numUsers;
        
        document.getElementById('per-user-price').textContent = '$' + perUserPrice.toFixed(3);
        document.getElementById('monthly-total').textContent = '$' + monthlyTotal.toFixed(2);
    }
    
    // Initialize the pricing section
    function initPricingSection() {
        const pricingSection = document.getElementById('pricing-section');
        if (!pricingSection) return;
        
        // Set up the calculator inputs
        const numSitesInput = document.getElementById('num-sites');
        const numUsersInput = document.getElementById('num-users');
        
        if (numSitesInput && numUsersInput) {
            numSitesInput.addEventListener('input', updateCalculator);
            numUsersInput.addEventListener('input', updateCalculator);
            
            // Initial calculation
            updateCalculator();
        }
        
        // Draw the graph
        drawPricingGraph();
    }
    
    // Toggle function for pricing section
    window.togglePricingSection = function() {
        const pricingSection = document.getElementById('pricing-section');
        const toggleBtn = document.getElementById('togglePricingBtn');
        
        if (pricingSection.style.display === 'none') {
            pricingSection.style.display = 'block';
            toggleBtn.textContent = 'Hide Pricing Model';
            drawPricingGraph(); // Redraw graph when shown
        } else {
            pricingSection.style.display = 'none';
            toggleBtn.textContent = 'View Pricing Model';
        }
    };
    
    // Initialize if the section exists
    initPricingSection();
}); 