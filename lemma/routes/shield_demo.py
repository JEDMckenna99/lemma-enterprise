"""
Lemma shield Demo Routes
Demonstrates the new automatic verification shieldway
"""

from flask import Blueprint, render_template, request, session, jsonify
from lemma.routes.api import require_api_key

shield_demo = Blueprint('shield_demo', __name__)

@shield_demo.route('/shield-demo')
def shield_demo_page():
    """
    Demo page showing the new Lemma shield in action
    """
    return render_template('shield_demo.html')

@shield_demo.route('/shield-demo-legacy')
def shield_demo_legacy():
    """
    Legacy demo page for backwards compatibility
    """
    return render_template('protected_shield_example.html')

@shield_demo.route('/shield-integration-guide')
def integration_guide():
    """
    Show the integration guide for developers
    """
    return render_template('shield_integration_guide.html')

@shield_demo.route('/api/shield-status')
def shield_status():
    """
    API endpoint to check the current shield status
    """
    return jsonify({
        'status': 'operational',
        'version': '1.0.0',
        'features': {
            'auto_verification': True,
            'background_checking': True,
            'agent_optimization': True,
            'network_effects': True
        },
        'network': {
            'total_sites': 1247,  # Example network size
            'verified_users': 89342,
            'agents': 3421
        }
    })

@shield_demo.route('/api/verify-agent', methods=['POST'])
@require_api_key
def verify_agent():
    """
    Enhanced verification endpoint optimized for agent workflows
    """
    try:
        data = request.get_json()
        presentation = data.get('presentation')
        challenge = data.get('challenge')
        
        # TODO: Integrate with your existing credential verification
        # This would use the same logic as /api/verify-human but with
        # additional agent-specific features
        
        # For demo purposes, return success
        agent_id = "agent_" + str(hash(str(presentation)))[-8:]
        
        # Set agent session
        session['verified_human'] = True
        session['agent_verified'] = True
        session['agent_id'] = agent_id
        
        return jsonify({
            'success': True,
            'verified': True,
            'agent_features': {
                'bulk_operations': True,
                'higher_rate_limits': True,
                'cross_platform_access': True,
                'audit_logging': True
            },
            'agent_id': agent_id
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@shield_demo.route('/api/network-metrics')
def network_metrics():
    """
    Provide network metrics for monitoring and analytics
    """
    return jsonify({
        'network_size': 1247,
        'growth_rate': '12% monthly',
        'verification_success_rate': 98.7,
        'average_verification_time': '1.2s',
        'top_integrations': [
            {'platform': 'E-commerce', 'sites': 342},
            {'platform': 'Social', 'sites': 298},
            {'platform': 'Professional Services', 'sites': 187},
            {'platform': 'Content Platforms', 'sites': 156},
            {'platform': 'Gaming', 'sites': 134}
        ],
        'agent_statistics': {
            'total_agents': 3421,
            'active_agents': 2847,
            'cross_platform_workflows': 1923,
            'avg_platforms_per_agent': 4.2
        }
    })

@shield_demo.route('/demo/scenarios')
def demo_scenarios():
    """
    Interactive demo showing different shield scenarios
    """
    scenario = request.args.get('scenario', 'success')
    
    scenarios = {
        'success': {
            'title': 'Successful Verification',
            'description': 'User has valid credentials and passes through seamlessly',
            'simulate': 'verified'
        },
        'no_credentials': {
            'title': 'No Credentials Found',
            'description': 'User needs to complete initial verification',
            'simulate': 'shield'
        },
        'revoked': {
            'title': 'Revoked Credential',
            'description': 'User\'s credential has been revoked',
            'simulate': 'error'
        },
        'network_error': {
            'title': 'Network Issues',
            'description': 'Verification server temporarily unavailable',
            'simulate': 'retry'
        },
        'agent_workflow': {
            'title': 'Professional Agent',
            'description': 'Agent accessing platform for client work',
            'simulate': 'agent'
        }
    }
    
    current_scenario = scenarios.get(scenario, scenarios['success'])
    
    return render_template('shield_scenario_demo.html', 
                         scenario=current_scenario,
                         all_scenarios=scenarios) 
