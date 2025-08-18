/**
 * Essential Lemma React Components
 * Streamlined components for professional functionality
 * Integrates seamlessly with the professional design system
 */

// React and ReactDOM from CDN (loaded in templates)
const { createElement: h, useState, useEffect, Fragment } = React;
const { createRoot } = ReactDOM;

// Utility functions
const cn = (...classes) => classes.filter(Boolean).join(' ');
const formatNumber = (num) => num.toLocaleString();
const formatCurrency = (amount) => new Intl.NumberFormat('en-US', { 
  style: 'currency', 
  currency: 'USD' 
}).format(amount);

// Simple API client
const api = {
  async get(url) {
    try {
      const response = await fetch(url);
      return response.ok ? response.json() : { error: true };
    } catch (error) {
      return { error: true };
    }
  },
  async post(url, data) {
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      });
      return response.ok ? response.json() : { error: true };
    } catch (error) {
      return { error: true };
    }
  }
};

/**
 * LoadingSpinner Component
 */
const LoadingSpinner = ({ size = 'md', className = '', text }) => {
  const sizeClasses = {
    sm: 'w-4 h-4 border-2',
    md: 'w-8 h-8 border-3',
    lg: 'w-12 h-12 border-4'
  };

  return h('div', { 
    className: `flex flex-col items-center justify-center ${className}`,
    style: { padding: '20px' }
  }, [
    h('div', {
      key: 'spinner',
      className: 'spinner',
      style: {
        width: size === 'sm' ? '16px' : size === 'lg' ? '48px' : '32px',
        height: size === 'sm' ? '16px' : size === 'lg' ? '48px' : '32px',
        border: '3px solid var(--gray-200)',
        borderTopColor: 'var(--primary-500)',
        borderRadius: '50%',
        animation: 'spin 1s linear infinite'
      }
    }),
    text && h('p', {
      key: 'text',
      style: {
        marginTop: '12px',
        color: 'var(--gray-500)',
        fontSize: 'var(--font-size-sm)'
      }
    }, text)
  ]);
};

/**
 * StatusCard Component - Professional status display
 */
const StatusCard = ({ type = 'info', icon, title, message, className = '' }) => {
  const typeClasses = {
    success: 'status-card success',
    warning: 'status-card warning', 
    error: 'status-card error',
    info: 'status-card info'
  };

  const icons = {
    success: '✓',
    warning: '⚠',
    error: '✕',
    info: 'ℹ'
  };

  return h('div', {
    className: `${typeClasses[type]} ${className}`
  }, [
    h('div', {
      key: 'icon',
      className: 'status-icon'
    }, icon || icons[type]),
    h('div', {
      key: 'content', 
      className: 'status-content'
    }, [
      h('h4', { key: 'title' }, title),
      message && h('p', { key: 'message' }, message)
    ])
  ]);
};

/**
 * MetricCard Component - Display key metrics
 */
const MetricCard = ({ 
  title, 
  value, 
  subtitle, 
  trend, 
  icon,
  className = '' 
}) => {
  return h('div', {
    className: `metric-card ${className}`
  }, [
    h('div', {
      key: 'label',
      className: 'metric-label'
    }, title),
    h('div', {
      key: 'value',
      className: 'metric-value'
    }, value),
    subtitle && h('div', {
      key: 'subtitle',
      className: 'metric-subtitle'
    }, subtitle),
    trend && h('div', {
      key: 'trend',
      className: `metric-trend ${trend > 0 ? 'positive' : trend < 0 ? 'negative' : 'neutral'}`,
      style: {
        fontSize: 'var(--font-size-sm)',
        color: trend > 0 ? 'var(--success)' : trend < 0 ? 'var(--error)' : 'var(--gray-500)',
        marginTop: 'var(--space-1)'
      }
    }, `${trend > 0 ? '↑' : trend < 0 ? '↓' : '→'} ${Math.abs(trend)}%`)
  ]);
};

/**
 * DemoSection Component - Interactive demo display
 */
const DemoSection = ({ 
  title,
  description,
  status,
  buttons = [],
  className = ''
}) => {
  return h('div', {
    className: `demo-card ${className}`
  }, [
    h('div', {
      key: 'header',
      className: 'demo-header'
    }, [
      h('h3', {
        key: 'title',
        className: 'demo-title'
      }, title),
      status && h('div', {
        key: 'badge',
        className: 'demo-badge'
      }, status)
    ]),
    description && h('p', {
      key: 'description',
      className: 'demo-description'
    }, description),
    buttons.length > 0 && h('div', {
      key: 'buttons',
      className: 'demo-buttons'
    }, buttons.map((button, index) => 
      h('a', {
        key: index,
        href: button.href,
        className: `btn ${button.variant || 'btn-primary'} ${button.className || ''}`,
        onClick: button.onClick
      }, button.label)
    ))
  ]);
};

/**
 * SimpleForm Component - Basic form wrapper with validation
 */
const SimpleForm = ({ 
  onSubmit,
  children,
  isLoading = false,
  className = ''
}) => {
  const handleSubmit = (e) => {
    e.preventDefault();
    if (!isLoading && onSubmit) {
      onSubmit(e);
    }
  };

  return h('form', {
    className: `form-container ${className}`,
    onSubmit: handleSubmit
  }, [
    h('div', {
      key: 'form-content'
    }, children),
    isLoading && h(LoadingSpinner, {
      key: 'loading',
      text: 'Processing...',
      className: 'mt-4'
    })
  ]);
};

/**
 * SystemStatus Component - Display system health
 */
const SystemStatus = ({ className = '' }) => {
  const [status, setStatus] = useState({
    loading: true,
    shield: 'unknown',
    engine: 'unknown', 
    stripe: 'unknown'
  });

  useEffect(() => {
    const checkStatus = async () => {
      const result = await api.get('/api/health');
      
      if (result.error) {
        setStatus({
          loading: false,
          shield: 'error',
          engine: 'error',
          stripe: 'error'
        });
      } else {
        setStatus({
          loading: false,
          shield: result.components?.lemma_shield ? 'active' : 'offline',
          engine: result.components?.rust_engine ? 'available' : 'fallback',
          stripe: result.components?.stripe_identity ? 'configured' : 'not-setup'
        });
      }
    };

    checkStatus();
  }, []);

  if (status.loading) {
    return h(LoadingSpinner, { text: 'Checking system status...' });
  }

  const getStatusType = (value) => {
    if (value === 'active' || value === 'available' || value === 'configured') return 'success';
    if (value === 'fallback' || value === 'not-setup') return 'warning';
    return 'error';
  };

  const getStatusText = (key, value) => {
    const texts = {
      shield: {
        active: '✅ Active',
        offline: '❌ Offline',
        error: '❌ Error'
      },
      engine: {
        available: '✅ Available',
        fallback: '⚠️ Fallback',
        error: '❌ Error'
      },
      stripe: {
        configured: '✅ Configured',
        'not-setup': '⚠️ Not setup',
        error: '❌ Error'
      }
    };
    return texts[key][value] || '❓ Unknown';
  };

  return h('div', {
    className: `card-grid card-grid-3 ${className}`
  }, [
    h(StatusCard, {
      key: 'shield',
      type: getStatusType(status.shield),
      title: 'Shield Status',
      message: getStatusText('shield', status.shield)
    }),
    h(StatusCard, {
      key: 'engine', 
      type: getStatusType(status.engine),
      title: 'Rust Engine',
      message: getStatusText('engine', status.engine)
    }),
    h(StatusCard, {
      key: 'stripe',
      type: getStatusType(status.stripe),
      title: 'Stripe Identity',
      message: getStatusText('stripe', status.stripe)
    })
  ]);
};

/**
 * Component Registry - Easy integration into templates
 */
window.LemmaComponents = {
  LoadingSpinner,
  StatusCard,
  MetricCard,
  DemoSection,
  SimpleForm,
  SystemStatus,
  
  // Mount function for easy integration
  mount: (componentName, elementId, props = {}) => {
    const element = document.getElementById(elementId);
    if (element && window.LemmaComponents[componentName]) {
      const root = createRoot(element);
      root.render(h(window.LemmaComponents[componentName], props));
      return root;
    }
    console.error(`Component ${componentName} or element ${elementId} not found`);
  },

  // Mount all components with data attributes
  mountAll: () => {
    document.querySelectorAll('[data-lemma-component]').forEach(element => {
      const componentName = element.dataset.lemmaComponent;
      const props = element.dataset.lemmaProps ? 
        JSON.parse(element.dataset.lemmaProps) : {};
      
      if (window.LemmaComponents[componentName]) {
        const root = createRoot(element);
        root.render(h(window.LemmaComponents[componentName], props));
      }
    });
  }
};

// Auto-mount components when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
  if (typeof React !== 'undefined') {
    window.LemmaComponents.mountAll();
    console.log('✅ Lemma React Components loaded successfully!');
  }
});

// Export for potential module usage
if (typeof module !== 'undefined' && module.exports) {
  module.exports = window.LemmaComponents;
} 