// Express middleware types (defined here to avoid dependency issues)
interface ExpressRequest {
  headers: { [key: string]: string | string[] | undefined };
  cookies?: { [key: string]: string };
  session?: any;
  query: { [key: string]: string | string[] | undefined };
  body: any;
  ip?: string;
  path: string;
  secure: boolean;
}

interface ExpressResponse {
  redirect(url: string): void;
  status(code: number): ExpressResponse;
  json(obj: any): void;
  cookie(name: string, value: string, options?: any): void;
}

interface ExpressNextFunction {
  (error?: any): void;
}

import { LemmaClient } from './client';
import {
  LemmaConfig,
  LemmaMiddlewareOptions,
  LemmaRequest,
  VerificationError,
  NetworkError
} from './types';

/**
 * Express middleware for Lemma human verification
 * 
 * @example
 * ```javascript
 * const { lemmaMiddleware } = require('@lemma-network/verifier');
 * 
 * app.use(lemmaMiddleware({
 *   instanceUrl: 'https://your-lemma-instance.com',
 *   apiKey: 'your-api-key'
 * }));
 * 
 * // Protected route
 * app.get('/protected', (req, res) => {
 *   if (req.lemma?.isVerified) {
 *     res.send('Welcome, verified human!');
 *   } else {
 *     res.redirect('/verify');
 *   }
 * });
 * ```
 */
export function lemmaMiddleware(config: LemmaConfig, options: LemmaMiddlewareOptions = {}) {
  const client = new LemmaClient(config);
  
  return async (req: LemmaRequest & ExpressRequest, res: ExpressResponse, next: ExpressNextFunction) => {
    try {
      // Initialize lemma object on request
      req.lemma = {
        isVerified: false,
        credential: undefined,
        userId: undefined
      };

      // Check for verification in session first
      if (req.session && req.session.lemmaVerified) {
        req.lemma.isVerified = true;
        req.lemma.userId = req.session.lemmaUserId;
        return next();
      }

      // Check for Lemma verification header or cookie
      const authHeader = req.headers['x-lemma-verification'] as string;
      const presentationData = authHeader || req.cookies?.lemma_presentation;

      if (presentationData) {
        try {
          const presentation = JSON.parse(presentationData);
          const challenge = (req.headers['x-lemma-challenge'] as string) || 
                           req.cookies?.lemma_challenge ||
                           (req.query.challenge as string);

          if (challenge) {
            const result = await client.verifyPresentation(presentation, challenge);
            
            if (result.verified) {
              req.lemma.isVerified = true;
              req.lemma.credential = presentation.verifiableCredential[0];
              req.lemma.userId = presentation.holder;

              // Store in session if available
              if (req.session) {
                req.session.lemmaVerified = true;
                req.session.lemmaUserId = presentation.holder;
              }
            }
          }
        } catch (error) {
          console.warn('Failed to verify Lemma presentation:', error);
        }
      }

      // Handle unverified users
      if (!req.lemma.isVerified && options.required) {
        if (options.redirectTo) {
          return res.redirect(options.redirectTo);
        }
        
        if (options.onError) {
          return options.onError(req, res, next, new VerificationError('Human verification required'));
        }

        return res.status(401).json({
          error: 'Human verification required',
          message: 'Please verify that you are human to access this resource',
          verificationUrl: `${config.instanceUrl}/verify`
        });
      }

      next();
    } catch (error) {
      console.error('Lemma middleware error:', error);
      
      if (options.onError) {
        return options.onError(req, res, next, error as Error);
      }

      res.status(500).json({
        error: 'Verification service error',
        message: 'Unable to verify human status'
      });
    }
  };
}

/**
 * Express route handler that requires Lemma verification
 * 
 * @example
 * ```javascript
 * const { requireLemmaVerification } = require('@lemma-network/verifier');
 * 
 * app.get('/protected', 
 *   requireLemmaVerification({ instanceUrl: 'https://your-lemma-instance.com' }),
 *   (req, res) => {
 *     res.send(`Welcome, verified human! User ID: ${req.lemma.userId}`);
 *   }
 * );
 * ```
 */
export function requireLemmaVerification(config: LemmaConfig, options: LemmaMiddlewareOptions = {}) {
  return lemmaMiddleware(config, { ...options, required: true });
}

/**
 * Express route to handle Lemma verification callback
 * This endpoint should be integrated into your application to handle post-verification redirects
 * 
 * @example
 * ```javascript
 * const { lemmaCallbackHandler } = require('@lemma-network/verifier');
 * 
 * app.post('/auth/lemma/callback', 
 *   lemmaCallbackHandler({ instanceUrl: 'https://your-lemma-instance.com' }),
 *   (req, res) => {
 *     if (req.lemma?.isVerified) {
 *       res.redirect('/dashboard');
 *     } else {
 *       res.redirect('/verify?error=verification_failed');
 *     }
 *   }
 * );
 * ```
 */
export function lemmaCallbackHandler(config: LemmaConfig) {
  const client = new LemmaClient(config);
  
  return async (req: LemmaRequest & ExpressRequest, res: ExpressResponse, next: ExpressNextFunction) => {
    try {
      req.lemma = {
        isVerified: false,
        credential: undefined,
        userId: undefined
      };

      const { presentation, challenge } = req.body;
      
      if (!presentation || !challenge) {
        return res.status(400).json({
          error: 'Missing verification data',
          message: 'Presentation and challenge are required'
        });
      }

      const result = await client.verifyPresentation(presentation, challenge);
      
      if (result.verified) {
        req.lemma.isVerified = true;
        req.lemma.credential = presentation.verifiableCredential[0];
        req.lemma.userId = presentation.holder;

        // Store in session
        if (req.session) {
          req.session.lemmaVerified = true;
          req.session.lemmaUserId = presentation.holder;
        }

        // Set secure cookies
        res.cookie('lemma_verified', 'true', {
          httpOnly: true,
          secure: req.secure,
          sameSite: 'strict',
          maxAge: 30 * 60 * 1000 // 30 minutes
        });

        res.cookie('lemma_user_id', presentation.holder, {
          httpOnly: true,
          secure: req.secure,
          sameSite: 'strict',
          maxAge: 30 * 60 * 1000 // 30 minutes
        });
      }

      next();
    } catch (error) {
      console.error('Lemma callback error:', error);
      res.status(500).json({
        error: 'Verification failed',
        message: 'Unable to process verification callback'
      });
    }
  };
}

/**
 * Utility function to check if a request is from a verified human
 */
export function isVerifiedHuman(req: LemmaRequest): boolean {
  return req.lemma?.isVerified === true;
}

/**
 * Utility function to get the verified user ID from a request
 */
export function getVerifiedUserId(req: LemmaRequest): string | undefined {
  return req.lemma?.userId;
}

/**
 * Middleware to log verification events for analytics
 */
export function lemmaAnalyticsMiddleware(config: LemmaConfig) {
  return (req: LemmaRequest & ExpressRequest, res: ExpressResponse, next: ExpressNextFunction) => {
    if (req.lemma?.isVerified) {
      // Log verification event (implement based on your analytics needs)
      console.log('Lemma verification event:', {
        userId: req.lemma.userId,
        timestamp: new Date().toISOString(),
        userAgent: req.headers['user-agent'],
        ip: req.ip,
        path: req.path
      });
    }
    next();
  };
} 