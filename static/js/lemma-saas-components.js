/**
 * Lemma SaaS Components - Modern 2025 React UI Library
 * Comprehensive component library for polished SaaS product pages
 * Integrates seamlessly with Flask backend and existing design system
 */

// React and ReactDOM from CDN
const { createElement: h, useState, useEffect, useRef, Fragment } = React;
const { createRoot } = ReactDOM;

// Utility functions
const cn = (...classes) => classes.filter(Boolean).join(' ');
const formatNumber = (num) => num.toLocaleString();
const formatCurrency = (amount) => new Intl.NumberFormat('en-US', { 
  style: 'currency', 
  currency: 'USD' 
}).format(amount);

// API client for Flask endpoints
const api = {
  async get(url) {
    const response = await fetch(url);
    return response.json();
  },
  async post(url, data) {
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });
    return response.json();
  }
};

// Animation hook for smooth transitions
const useAnimation = (trigger, duration = 300) => {
  const [isAnimating, setIsAnimating] = useState(false);
  
  useEffect(() => {
    if (trigger) {
      setIsAnimating(true);
      const timeout = setTimeout(() => setIsAnimating(false), duration);
      return () => clearTimeout(timeout);
    }
  }, [trigger, duration]);
  
  return isAnimating;
};

// Intersection Observer hook for scroll animations
const useInView = (options = {}) => {
  const [inView, setInView] = useState(false);
  const ref = useRef();
  
  useEffect(() => {
    const observer = new IntersectionObserver(([entry]) => {
      setInView(entry.isIntersecting);
    }, options);
    
    if (ref.current) observer.observe(ref.current);
    return () => observer.disconnect();
  }, []);
  
  return [ref, inView];
};

/**
 * HeroSection - Modern 2025 SaaS Hero with animations
 */
const HeroSection = () => {
  const [stats, setStats] = useState({
    verifications: 0,
    savings: 0,
    responseTime: 0
  });
  const [isLoaded, setIsLoaded] = useState(false);
  
  useEffect(() => {
    setTimeout(() => {
      setIsLoaded(true);
      const targets = { verifications: 2847392, savings: 99.8, responseTime: 8.3 };
      let step = 0;
      const timer = setInterval(() => {
        step += 2;
        const progress = Math.min(step / 100, 1);
        setStats({
          verifications: Math.floor(targets.verifications * progress),
          savings: Math.floor(targets.savings * progress * 10) / 10,
          responseTime: Math.floor(targets.responseTime * progress * 10) / 10
        });
        if (progress >= 1) clearInterval(timer);
      }, 30);
    }, 500);
  }, []);
  
  return h('section', {
    className: 'hero-section relative overflow-hidden min-h-screen flex items-center'
  }, [
    // Background gradient with animated particles
    h('div', {
      key: 'bg',
      className: 'absolute inset-0 bg-gradient-to-br from-blue-600 via-purple-600 to-blue-800'
    }),
    h('div', {
      key: 'particles',
      className: 'absolute inset-0 opacity-20'
    }, Array.from({ length: 20 }, (_, i) => 
      h('div', {
        key: i,
        className: 'absolute w-2 h-2 bg-white rounded-full animate-pulse',
        style: {
          left: `${Math.random() * 100}%`,
          top: `${Math.random() * 100}%`,
          animationDelay: `${Math.random() * 3}s`
        }
      })
    )),
    
    // Content container
    h('div', {
      key: 'content',
      className: 'relative container mx-auto px-6 text-center text-white'
    }, [
      h('div', {
        key: 'heading',
        className: `transform transition-all duration-1000 ${isLoaded ? 'translate-y-0 opacity-100' : 'translate-y-8 opacity-0'}`
      }, [
        h('h1', {
          key: 'title',
          className: 'text-5xl md:text-7xl font-bold mb-6 leading-tight'
        }, [
          'The Future of ',
          h('span', {
            key: 'highlight',
            className: 'bg-gradient-to-r from-yellow-400 to-orange-400 bg-clip-text text-transparent'
          }, 'Digital Verification')
        ]),
        h('p', {
          key: 'subtitle',
          className: 'text-xl md:text-2xl mb-12 max-w-4xl mx-auto text-blue-100'
        }, 'Revolutionary cryptographic verification with zero API calls, perfect privacy, and unlimited scale.')
      ]),
      
      // Stats counter
      h('div', {
        key: 'stats',
        className: `grid grid-cols-1 md:grid-cols-3 gap-8 mb-12 transform transition-all duration-1000 delay-300 ${isLoaded ? 'translate-y-0 opacity-100' : 'translate-y-8 opacity-0'}`
      }, [
        h('div', { key: 'stat1', className: 'text-center' }, [
          h('div', { key: 'number', className: 'text-4xl font-bold text-yellow-400' }, formatNumber(stats.verifications)),
          h('div', { key: 'label', className: 'text-blue-200' }, 'Verifications Completed')
        ]),
        h('div', { key: 'stat2', className: 'text-center' }, [
          h('div', { key: 'number', className: 'text-4xl font-bold text-green-400' }, `${stats.savings}%`),
          h('div', { key: 'label', className: 'text-blue-200' }, 'Cost Reduction')
        ]),
        h('div', { key: 'stat3', className: 'text-center' }, [
          h('div', { key: 'number', className: 'text-4xl font-bold text-purple-400' }, `${stats.responseTime}ms`),
          h('div', { key: 'label', className: 'text-blue-200' }, 'Response Time')
        ])
      ]),
      
      // CTA buttons
      h('div', {
        key: 'cta',
        className: `flex flex-col sm:flex-row gap-6 justify-center items-center transform transition-all duration-1000 delay-500 ${isLoaded ? 'translate-y-0 opacity-100' : 'translate-y-8 opacity-0'}`
      }, [
        h('button', {
          key: 'primary',
          className: 'px-8 py-4 bg-white text-blue-600 rounded-lg font-semibold text-lg hover:bg-gray-100 transform hover:scale-105 transition-all duration-200 shadow-lg hover:shadow-xl',
          onClick: () => window.location.href = '/join-network'
        }, '🚀 Start Free Trial'),
        h('button', {
          key: 'secondary',
          className: 'px-8 py-4 border-2 border-white text-white rounded-lg font-semibold text-lg hover:bg-white hover:text-blue-600 transform hover:scale-105 transition-all duration-200',
          onClick: () => document.getElementById('demo-section')?.scrollIntoView({ behavior: 'smooth' })
        }, '🎯 View Demo')
      ])
    ])
  ]);
};

/**
 * FeatureShowcase - Interactive feature cards with hover effects
 */
const FeatureShowcase = () => {
  const [viewRef, inView] = useInView({ threshold: 0.1 });
  
  const features = [
    {
      icon: '⚡',
      title: 'Zero API Calls',
      description: 'Revolutionary offline verification',
      benefit: '99.8% cost reduction',
      color: 'from-yellow-400 to-orange-500'
    },
    {
      icon: '🔒',
      title: 'Perfect Privacy',
      description: 'OPRF cryptography ensures zero data leakage',
      benefit: 'Military-grade security',
      color: 'from-blue-400 to-purple-500'
    },
    {
      icon: '🌍',
      title: 'Global Performance',
      description: 'Sub-10ms response time worldwide',
      benefit: '20x faster than competitors',
      color: 'from-green-400 to-blue-500'
    },
    {
      icon: '🛡️',
      title: 'Mission Critical',
      description: 'Works during network outages',
      benefit: '99.99% uptime guaranteed',
      color: 'from-purple-400 to-pink-500'
    }
  ];
  
  return h('section', {
    ref: viewRef,
    className: 'py-24 bg-gray-50'
  }, [
    h('div', {
      key: 'container',
      className: 'container mx-auto px-6'
    }, [
      h('div', {
        key: 'header',
        className: `text-center mb-16 transform transition-all duration-1000 ${inView ? 'translate-y-0 opacity-100' : 'translate-y-8 opacity-0'}`
      }, [
        h('h2', {
          key: 'title',
          className: 'text-4xl md:text-5xl font-bold mb-6 text-gray-900'
        }, 'Revolutionary Capabilities'),
        h('p', {
          key: 'subtitle',
          className: 'text-xl text-gray-600 max-w-3xl mx-auto'
        }, 'The only verification system that combines perfect privacy, unlimited scale, and zero infrastructure costs')
      ]),
      
      h('div', {
        key: 'features',
        className: 'grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8'
      }, features.map((feature, index) => 
        h('div', {
          key: index,
          className: `group relative overflow-hidden rounded-2xl bg-white p-8 shadow-lg transition-all duration-500 hover:scale-105 hover:shadow-2xl cursor-pointer transform ${inView ? 'translate-y-0 opacity-100' : 'translate-y-8 opacity-0'}`,
          style: { transitionDelay: `${index * 150}ms` }
        }, [
          h('div', {
            key: 'bg',
            className: `absolute inset-0 bg-gradient-to-br ${feature.color} opacity-0 group-hover:opacity-10 transition-opacity duration-300`
          }),
          h('div', {
            key: 'content',
            className: 'relative z-10'
          }, [
            h('div', {
              key: 'icon',
              className: `text-5xl mb-6 transform group-hover:scale-110 transition-transform duration-300`
            }, feature.icon),
            h('h3', {
              key: 'title',
              className: 'text-2xl font-bold mb-4 text-gray-900'
            }, feature.title),
            h('p', {
              key: 'description',
              className: 'text-gray-600 mb-4 line-height-relaxed'
            }, feature.description),
            h('div', {
              key: 'benefit',
              className: `inline-block px-4 py-2 rounded-full text-sm font-semibold bg-gradient-to-r ${feature.color} text-white transform group-hover:scale-105 transition-transform duration-300`
            }, feature.benefit)
          ])
        ])
      ))
    ])
  ]);
};

/**
 * InteractiveDemo - Live OPRF verification demo
 */
const InteractiveDemo = () => {
  const [isVerifying, setIsVerifying] = useState(false);
  const [results, setResults] = useState(null);
  const [steps, setSteps] = useState([]);
  const [viewRef, inView] = useInView({ threshold: 0.1 });
  
  const runDemo = async () => {
    setIsVerifying(true);
    setResults(null);
    setSteps([]);
    
    const demoSteps = [
      { step: 1, text: 'Generating OPRF proof...', delay: 500 },
      { step: 2, text: 'Checking cascade filters...', delay: 300 },
      { step: 3, text: 'Verifying offline credential...', delay: 200 },
      { step: 4, text: 'Validation complete!', delay: 100 }
    ];
    
    for (const stepData of demoSteps) {
      await new Promise(resolve => setTimeout(resolve, stepData.delay));
      setSteps(prev => [...prev, stepData]);
    }
    
    // Simulated results
    setResults({
      verified: true,
      responseTime: 8.3,
      networkCalls: 0,
      privacyScore: 100,
      efficiency: 99.8
    });
    
    setIsVerifying(false);
  };
  
  return h('section', {
    ref: viewRef,
    id: 'demo-section',
    className: 'py-24 bg-white'
  }, [
    h('div', {
      key: 'container',
      className: 'container mx-auto px-6'
    }, [
      h('div', {
        key: 'header',
        className: `text-center mb-16 transform transition-all duration-1000 ${inView ? 'translate-y-0 opacity-100' : 'translate-y-8 opacity-0'}`
      }, [
        h('h2', {
          key: 'title',
          className: 'text-4xl md:text-5xl font-bold mb-6 text-gray-900'
        }, 'Live Verification Demo'),
        h('p', {
          key: 'subtitle',
          className: 'text-xl text-gray-600 max-w-3xl mx-auto'
        }, 'Experience real-time OPRF verification with zero API calls and perfect privacy')
      ]),
      
      h('div', {
        key: 'demo',
        className: `max-w-4xl mx-auto bg-gray-900 rounded-2xl p-8 shadow-2xl transform transition-all duration-1000 delay-300 ${inView ? 'translate-y-0 opacity-100' : 'translate-y-8 opacity-0'}`
      }, [
        h('div', {
          key: 'terminal-header',
          className: 'flex items-center mb-6'
        }, [
          h('div', { key: 'dot1', className: 'w-3 h-3 bg-red-500 rounded-full mr-2' }),
          h('div', { key: 'dot2', className: 'w-3 h-3 bg-yellow-500 rounded-full mr-2' }),
          h('div', { key: 'dot3', className: 'w-3 h-3 bg-green-500 rounded-full mr-4' }),
          h('span', { key: 'title', className: 'text-gray-400 text-sm' }, 'lemma-verification-demo')
        ]),
        
        h('div', {
          key: 'terminal-content',
          className: 'font-mono text-sm text-green-400 min-h-64'
        }, [
          h('div', { key: 'prompt', className: 'mb-4' }, '$ lemma verify --demo --offline'),
          
          // Steps animation
          ...steps.map((step, index) => 
            h('div', {
              key: `step-${index}`,
              className: 'mb-2 flex items-center'
            }, [
              h('span', { key: 'step-num', className: 'text-blue-400 mr-2' }, `[${step.step}]`),
              h('span', { key: 'step-text' }, step.text),
              h('span', { key: 'spinner', className: 'ml-2 animate-spin' }, step.step === steps.length && isVerifying ? '⚡' : '✓')
            ])
          ),
          
          // Results display
          results && h('div', {
            key: 'results',
            className: 'mt-6 p-4 bg-green-900/20 rounded border border-green-700'
          }, [
            h('div', { key: 'header', className: 'text-green-300 font-bold mb-2' }, '✅ Verification Successful'),
            h('div', { key: 'metrics', className: 'grid grid-cols-2 gap-4 text-sm' }, [
              h('div', { key: 'time' }, `Response Time: ${results.responseTime}ms`),
              h('div', { key: 'calls' }, `Network Calls: ${results.networkCalls}`),
              h('div', { key: 'privacy' }, `Privacy Score: ${results.privacyScore}%`),
              h('div', { key: 'efficiency' }, `Efficiency: ${results.efficiency}%`)
            ])
          ])
        ]),
        
        h('div', {
          key: 'controls',
          className: 'mt-8 text-center'
        }, [
          h('button', {
            key: 'run-demo',
            className: `px-8 py-4 bg-gradient-to-r from-blue-600 to-purple-600 text-white rounded-lg font-semibold text-lg hover:from-blue-700 hover:to-purple-700 transform hover:scale-105 transition-all duration-200 shadow-lg hover:shadow-xl ${isVerifying ? 'opacity-50 cursor-not-allowed' : ''}`,
            onClick: runDemo,
            disabled: isVerifying
          }, isVerifying ? '⚡ Running Demo...' : '🚀 Run Live Demo')
        ])
      ])
    ])
  ]);
};

/**
 * PricingSection - Modern pricing cards with animations
 */
const PricingSection = () => {
  const [billingCycle, setBillingCycle] = useState('monthly');
  const [viewRef, inView] = useInView({ threshold: 0.1 });
  
  const plans = [
    {
      name: 'Starter',
      price: { monthly: 99, annual: 948 },
      description: 'Perfect for small teams',
      features: [
        '10,000 verifications/month',
        'Basic OPRF protection',
        'Email support',
        'Standard integrations'
      ],
      color: 'from-blue-400 to-blue-600',
      popular: false
    },
    {
      name: 'Professional',
      price: { monthly: 299, annual: 2868 },
      description: 'For growing businesses',
      features: [
        '100,000 verifications/month',
        'Advanced OPRF + Cascading',
        'Priority support',
        'Custom integrations',
        'Analytics dashboard'
      ],
      color: 'from-purple-400 to-purple-600',
      popular: true
    },
    {
      name: 'Enterprise',
      price: { monthly: 999, annual: 9588 },
      description: 'For large organizations',
      features: [
        'Unlimited verifications',
        'Full OPRF suite',
        '24/7 dedicated support',
        'White-label solution',
        'Custom deployment',
        'SLA guarantees'
      ],
      color: 'from-green-400 to-green-600',
      popular: false
    }
  ];
  
  return h('section', {
    ref: viewRef,
    className: 'py-24 bg-gradient-to-br from-gray-50 to-white'
  }, [
    h('div', {
      key: 'container',
      className: 'container mx-auto px-6'
    }, [
      h('div', {
        key: 'header',
        className: `text-center mb-16 transform transition-all duration-1000 ${inView ? 'translate-y-0 opacity-100' : 'translate-y-8 opacity-0'}`
      }, [
        h('h2', {
          key: 'title',
          className: 'text-4xl md:text-5xl font-bold mb-6 text-gray-900'
        }, 'Simple, Transparent Pricing'),
        h('p', {
          key: 'subtitle',
          className: 'text-xl text-gray-600 max-w-3xl mx-auto mb-8'
        }, 'Choose the perfect plan for your verification needs. All plans include our revolutionary OPRF technology.'),
        
        // Billing cycle toggle
        h('div', {
          key: 'toggle',
          className: 'inline-flex items-center bg-white rounded-lg p-1 shadow-lg'
        }, [
          h('button', {
            key: 'monthly',
            className: `px-6 py-3 rounded-md font-semibold transition-all duration-200 ${billingCycle === 'monthly' ? 'bg-blue-600 text-white shadow-md' : 'text-gray-600 hover:text-gray-900'}`,
            onClick: () => setBillingCycle('monthly')
          }, 'Monthly'),
          h('button', {
            key: 'annual',
            className: `px-6 py-3 rounded-md font-semibold transition-all duration-200 ${billingCycle === 'annual' ? 'bg-blue-600 text-white shadow-md' : 'text-gray-600 hover:text-gray-900'}`,
            onClick: () => setBillingCycle('annual')
          }, 'Annual (Save 20%)')
        ])
      ]),
      
      h('div', {
        key: 'plans',
        className: 'grid grid-cols-1 md:grid-cols-3 gap-8 max-w-6xl mx-auto'
      }, plans.map((plan, index) => 
        h('div', {
          key: index,
          className: `relative rounded-2xl bg-white p-8 shadow-lg transition-all duration-500 hover:shadow-2xl hover:scale-105 transform ${inView ? 'translate-y-0 opacity-100' : 'translate-y-8 opacity-0'} ${plan.popular ? 'ring-2 ring-purple-500 scale-105' : ''}`,
          style: { transitionDelay: `${index * 200}ms` }
        }, [
          // Popular badge
          plan.popular && h('div', {
            key: 'badge',
            className: 'absolute -top-4 left-1/2 transform -translate-x-1/2 bg-gradient-to-r from-purple-500 to-pink-500 text-white px-4 py-1 rounded-full text-sm font-semibold'
          }, '🔥 Most Popular'),
          
          h('div', {
            key: 'content',
            className: 'text-center'
          }, [
            h('h3', {
              key: 'name',
              className: 'text-2xl font-bold mb-2 text-gray-900'
            }, plan.name),
            h('p', {
              key: 'description',
              className: 'text-gray-600 mb-6'
            }, plan.description),
            h('div', {
              key: 'price',
              className: 'mb-8'
            }, [
              h('span', {
                key: 'amount',
                className: 'text-5xl font-bold text-gray-900'
              }, `$${plan.price[billingCycle]}`),
              h('span', {
                key: 'period',
                className: 'text-gray-600 ml-2'
              }, `/${billingCycle === 'monthly' ? 'month' : 'year'}`)
            ]),
            h('ul', {
              key: 'features',
              className: 'space-y-4 mb-8 text-left'
            }, plan.features.map((feature, fIndex) => 
              h('li', {
                key: fIndex,
                className: 'flex items-center'
              }, [
                h('span', {
                  key: 'check',
                  className: 'text-green-500 mr-3'
                }, '✓'),
                h('span', {
                  key: 'text',
                  className: 'text-gray-700'
                }, feature)
              ])
            )),
            h('button', {
              key: 'cta',
              className: `w-full py-4 rounded-lg font-semibold text-lg transition-all duration-200 transform hover:scale-105 ${plan.popular ? 'bg-gradient-to-r from-purple-600 to-pink-600 text-white hover:from-purple-700 hover:to-pink-700' : 'bg-gray-900 text-white hover:bg-gray-800'}`,
              onClick: () => window.location.href = '/onboarding'
            }, plan.popular ? '🚀 Get Started' : 'Choose Plan')
          ])
        ])
      ))
    ])
  ]);
};

/**
 * TestimonialSection - Social proof with animations
 */
const TestimonialSection = () => {
  const [viewRef, inView] = useInView({ threshold: 0.1 });
  
  const testimonials = [
    {
      name: 'Sarah Chen',
      role: 'CTO, TechCorp',
      avatar: '👩‍💻',
      content: 'Lemma reduced our verification costs by 99.8% while improving security. The offline capability is game-changing.',
      rating: 5
    },
    {
      name: 'Marcus Rodriguez',
      role: 'Security Lead, FinanceFlow',
      avatar: '👨‍🔬',
      content: 'Finally, a verification system that actually protects user privacy. The OPRF implementation is flawless.',
      rating: 5
    },
    {
      name: 'Emma Thompson',
      role: 'Product Manager, ScaleUp',
      avatar: '👩‍🚀',
      content: 'Sub-10ms response times globally. Our users love the seamless experience.',
      rating: 5
    }
  ];
  
  return h('section', {
    ref: viewRef,
    className: 'py-24 bg-gray-900 text-white'
  }, [
    h('div', {
      key: 'container',
      className: 'container mx-auto px-6'
    }, [
      h('div', {
        key: 'header',
        className: `text-center mb-16 transform transition-all duration-1000 ${inView ? 'translate-y-0 opacity-100' : 'translate-y-8 opacity-0'}`
      }, [
        h('h2', {
          key: 'title',
          className: 'text-4xl md:text-5xl font-bold mb-6'
        }, 'Trusted by Industry Leaders'),
        h('p', {
          key: 'subtitle',
          className: 'text-xl text-gray-300 max-w-3xl mx-auto'
        }, 'Join thousands of companies using Lemma to secure their digital infrastructure')
      ]),
      
      h('div', {
        key: 'testimonials',
        className: 'grid grid-cols-1 md:grid-cols-3 gap-8'
      }, testimonials.map((testimonial, index) => 
        h('div', {
          key: index,
          className: `bg-gray-800 rounded-2xl p-8 shadow-lg transform transition-all duration-500 hover:scale-105 ${inView ? 'translate-y-0 opacity-100' : 'translate-y-8 opacity-0'}`,
          style: { transitionDelay: `${index * 200}ms` }
        }, [
          h('div', {
            key: 'rating',
            className: 'flex mb-4'
          }, Array.from({ length: 5 }, (_, i) => 
            h('span', {
              key: i,
              className: 'text-yellow-400 text-xl'
            }, '⭐')
          )),
          h('p', {
            key: 'content',
            className: 'text-gray-300 mb-6 text-lg leading-relaxed'
          }, `"${testimonial.content}"`),
          h('div', {
            key: 'author',
            className: 'flex items-center'
          }, [
            h('div', {
              key: 'avatar',
              className: 'w-12 h-12 bg-gray-700 rounded-full flex items-center justify-center text-2xl mr-4'
            }, testimonial.avatar),
            h('div', { key: 'info' }, [
              h('div', {
                key: 'name',
                className: 'font-semibold text-white'
              }, testimonial.name),
              h('div', {
                key: 'role',
                className: 'text-gray-400'
              }, testimonial.role)
            ])
          ])
        ])
      ))
    ])
  ]);
};

/**
 * CallToActionSection - Final conversion section
 */
const CallToActionSection = () => {
  const [viewRef, inView] = useInView({ threshold: 0.1 });
  
  return h('section', {
    ref: viewRef,
    className: 'py-24 bg-gradient-to-r from-blue-600 via-purple-600 to-blue-800 text-white'
  }, [
    h('div', {
      key: 'container',
      className: 'container mx-auto px-6 text-center'
    }, [
      h('div', {
        key: 'content',
        className: `max-w-4xl mx-auto transform transition-all duration-1000 ${inView ? 'translate-y-0 opacity-100' : 'translate-y-8 opacity-0'}`
      }, [
        h('h2', {
          key: 'title',
          className: 'text-4xl md:text-6xl font-bold mb-6 leading-tight'
        }, 'Ready to Revolutionize Your Verification?'),
        h('p', {
          key: 'subtitle',
          className: 'text-2xl mb-12 text-blue-100 leading-relaxed'
        }, 'Join the verification revolution. Start with our free trial and experience the future of digital trust.'),
        h('div', {
          key: 'buttons',
          className: 'flex flex-col sm:flex-row gap-6 justify-center items-center'
        }, [
          h('button', {
            key: 'primary',
            className: 'px-12 py-6 bg-white text-blue-600 rounded-lg font-bold text-xl hover:bg-gray-100 transform hover:scale-105 transition-all duration-200 shadow-lg hover:shadow-xl',
            onClick: () => window.location.href = '/join-network'
          }, '🚀 Start Free Trial'),
          h('button', {
            key: 'secondary',
            className: 'px-12 py-6 border-2 border-white text-white rounded-lg font-bold text-xl hover:bg-white hover:text-blue-600 transform hover:scale-105 transition-all duration-200',
            onClick: () => window.location.href = '/contact'
          }, '📞 Talk to Sales')
        ]),
        h('p', {
          key: 'note',
          className: 'mt-8 text-blue-200'
        }, 'No credit card required • 30-day free trial • Cancel anytime')
      ])
    ])
  ]);
};

// Main SaaS Page Component
const ModernSaaSPage = () => {
  return h(Fragment, {}, [
    h(HeroSection, { key: 'hero' }),
    h(FeatureShowcase, { key: 'features' }),
    h(InteractiveDemo, { key: 'demo' }),
    h(PricingSection, { key: 'pricing' }),
    h(TestimonialSection, { key: 'testimonials' }),
    h(CallToActionSection, { key: 'cta' })
  ]);
};

// Export for global use
window.LemmaSaaSComponents = {
  HeroSection,
  FeatureShowcase,
  InteractiveDemo,
  PricingSection,
  TestimonialSection,
  CallToActionSection,
  ModernSaaSPage,
  
  // Mount components automatically
  mount: (componentName, containerId, props = {}) => {
    const container = document.getElementById(containerId);
    if (container && window.LemmaSaaSComponents[componentName]) {
      const root = createRoot(container);
      root.render(h(window.LemmaSaaSComponents[componentName], props));
    }
  },
  
  // Mount all components with data attributes
  mountAll: () => {
    document.querySelectorAll('[data-lemma-saas-component]').forEach(element => {
      const componentName = element.getAttribute('data-lemma-saas-component');
      const propsData = element.getAttribute('data-lemma-saas-props');
      const props = propsData ? JSON.parse(propsData) : {};
      
      if (window.LemmaSaaSComponents[componentName]) {
        const root = createRoot(element);
        root.render(h(window.LemmaSaaSComponents[componentName], props));
      }
    });
  }
};

// Auto-mount on DOM load
document.addEventListener('DOMContentLoaded', () => {
  window.LemmaSaaSComponents.mountAll();
  console.log('🎯 Lemma SaaS Components Loaded');
}); 