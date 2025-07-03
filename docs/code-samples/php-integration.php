<?php
/**
 * Lemma Enterprise PHP Integration Examples
 * Human Verification Protocol for PHP Applications
 * 
 * Supports Laravel, Symfony, and vanilla PHP with complete examples.
 */

namespace Lemma\Integration;

require_once 'vendor/autoload.php';

use Exception;
use GuzzleHttp\Client;
use GuzzleHttp\Exception\RequestException;
use Psr\Http\Message\ResponseInterface;

// ============================================================================
// CONFIGURATION
// ============================================================================

define('LEMMA_BASE_URL', 'https://lemma.id');
define('LEMMA_API_KEY', $_ENV['LEMMA_API_KEY'] ?? null);

if (!LEMMA_API_KEY) {
    throw new Exception("❌ LEMMA_API_KEY environment variable is required");
}

// ============================================================================
// LEMMA CLIENT CLASS
// ============================================================================

class LemmaClient
{
    private string $apiKey;
    private string $baseUrl;
    private Client $httpClient;

    public function __construct(string $apiKey, string $baseUrl = LEMMA_BASE_URL)
    {
        $this->apiKey = $apiKey;
        $this->baseUrl = rtrim($baseUrl, '/');
        
        $this->httpClient = new Client([
            'base_uri' => $this->baseUrl,
            'timeout' => 30,
            'headers' => [
                'X-API-Key' => $this->apiKey,
                'Content-Type' => 'application/json',
                'User-Agent' => 'Lemma-PHP-Client/1.0'
            ]
        ]);
    }

    /**
     * Generate a verification challenge
     */
    public function generateChallenge(): array
    {
        try {
            $response = $this->httpClient->get('/api/generate-challenge');
            $data = json_decode($response->getBody(), true);
            return $data['data'];
        } catch (RequestException $e) {
            throw new Exception("Failed to generate challenge: " . $e->getMessage());
        }
    }

    /**
     * Verify human credential presentation
     */
    public function verifyHuman(array $presentation, string $challenge, string $domain): array
    {
        try {
            $payload = [
                'presentation' => $presentation,
                'challenge' => $challenge,
                'domain' => $domain
            ];

            $response = $this->httpClient->post('/api/verify-human', [
                'json' => $payload
            ]);

            return json_decode($response->getBody(), true);
        } catch (RequestException $e) {
            throw new Exception("Human verification failed: " . $e->getMessage());
        }
    }

    /**
     * Get monthly usage metrics
     */
    public function getMonthlyUsage(int $year, int $month): array
    {
        try {
            $response = $this->httpClient->get('/api/billing/usage/monthly', [
                'query' => ['year' => $year, 'month' => $month]
            ]);

            $data = json_decode($response->getBody(), true);
            return $data['data'];
        } catch (RequestException $e) {
            throw new Exception("Failed to get usage metrics: " . $e->getMessage());
        }
    }

    /**
     * Check API health status
     */
    public function healthCheck(): array
    {
        try {
            $response = $this->httpClient->get('/api/health');
            return json_decode($response->getBody(), true);
        } catch (RequestException $e) {
            throw new Exception("Health check failed: " . $e->getMessage());
        }
    }

    /**
     * Issue a new credential (sandbox only for testing)
     */
    public function issueCredential(string $userId, string $verificationMethod = "sandbox"): array
    {
        try {
            $payload = [
                'user_id' => $userId,
                'verification_method' => $verificationMethod
            ];

            $response = $this->httpClient->post('/api/issue-credential', [
                'json' => $payload
            ]);

            return json_decode($response->getBody(), true);
        } catch (RequestException $e) {
            throw new Exception("Failed to issue credential: " . $e->getMessage());
        }
    }
}

// ============================================================================
// VANILLA PHP INTEGRATION
// ============================================================================

class VanillaPHPLemmaIntegration
{
    private LemmaClient $lemma;
    private string $domain;

    public function __construct(string $domain = 'localhost')
    {
        $this->lemma = new LemmaClient(LEMMA_API_KEY);
        $this->domain = $domain;
        
        // Start session if not already started
        if (session_status() === PHP_SESSION_NONE) {
            session_start();
        }
    }

    /**
     * Middleware function to require human verification
     */
    public function requireHuman(): bool
    {
        if (!isset($_SESSION['lemma_verified']) || !$_SESSION['lemma_verified']) {
            http_response_code(401);
            header('Content-Type: application/json');
            echo json_encode([
                'success' => false,
                'error' => 'Human verification required',
                'verify_url' => '/verify.php'
            ]);
            return false;
        }

        return true;
    }

    /**
     * Handle verification request
     */
    public function handleVerification(): array
    {
        if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
            throw new Exception('Method not allowed');
        }

        $input = json_decode(file_get_contents('php://input'), true);
        
        if (!$input || !isset($input['presentation']) || !isset($input['challenge'])) {
            throw new Exception('Missing presentation or challenge');
        }

        $result = $this->lemma->verifyHuman(
            $input['presentation'],
            $input['challenge'],
            $input['domain'] ?? $this->domain
        );

        if ($result['success'] && $result['data']['verified']) {
            $_SESSION['lemma_verified'] = true;
            $_SESSION['lemma_user_id'] = $result['data']['user_id'];
        }

        return $result;
    }

    /**
     * Generate challenge for frontend
     */
    public function generateChallenge(): array
    {
        return $this->lemma->generateChallenge();
    }

    /**
     * Get current user ID if verified
     */
    public function getCurrentUserId(): ?string
    {
        return $_SESSION['lemma_user_id'] ?? null;
    }
}

// ============================================================================
// LARAVEL INTEGRATION
// ============================================================================

/**
 * Laravel Service Provider for Lemma
 * Add to config/app.php in providers array
 */
class LemmaServiceProvider extends \Illuminate\Support\ServiceProvider
{
    public function register()
    {
        $this->app->singleton(LemmaClient::class, function ($app) {
            return new LemmaClient(config('lemma.api_key'));
        });
    }

    public function boot()
    {
        $this->publishes([
            __DIR__.'/config/lemma.php' => config_path('lemma.php'),
        ]);
    }
}

/**
 * Laravel Middleware for Lemma verification
 * Add to app/Http/Middleware/LemmaMiddleware.php
 */
class LemmaMiddleware
{
    private LemmaClient $lemma;

    public function __construct(LemmaClient $lemma)
    {
        $this->lemma = $lemma;
    }

    public function handle($request, \Closure $next)
    {
        if (!session('lemma_verified')) {
            return response()->json([
                'success' => false,
                'error' => 'Human verification required',
                'verify_url' => route('lemma.verify')
            ], 401);
        }

        $request->attributes->set('lemma_user_id', session('lemma_user_id'));
        return $next($request);
    }
}

/**
 * Laravel Controller for Lemma endpoints
 * Add to app/Http/Controllers/LemmaController.php
 */
class LemmaController extends \Illuminate\Routing\Controller
{
    private LemmaClient $lemma;

    public function __construct(LemmaClient $lemma)
    {
        $this->lemma = $lemma;
    }

    public function generateChallenge()
    {
        try {
            $challenge = $this->lemma->generateChallenge();
            return response()->json(['success' => true, 'data' => $challenge]);
        } catch (Exception $e) {
            return response()->json(['success' => false, 'error' => $e->getMessage()], 500);
        }
    }

    public function verifyHuman(\Illuminate\Http\Request $request)
    {
        try {
            $request->validate([
                'presentation' => 'required|array',
                'challenge' => 'required|string',
                'domain' => 'string'
            ]);

            $result = $this->lemma->verifyHuman(
                $request->input('presentation'),
                $request->input('challenge'),
                $request->input('domain', config('lemma.domain', 'localhost'))
            );

            if ($result['success'] && $result['data']['verified']) {
                session(['lemma_verified' => true]);
                session(['lemma_user_id' => $result['data']['user_id']]);
            }

            return response()->json($result);
        } catch (Exception $e) {
            return response()->json(['success' => false, 'error' => $e->getMessage()], 500);
        }
    }

    public function protectedContent(\Illuminate\Http\Request $request)
    {
        return response()->json([
            'message' => 'This content is only accessible to verified humans',
            'user_id' => $request->attributes->get('lemma_user_id'),
            'timestamp' => now()->toISOString(),
            'data' => [
                'secret' => 'Human-only content here',
                'user_privileges' => ['view_premium_content', 'post_comments', 'access_api']
            ]
        ]);
    }

    public function usageMetrics()
    {
        try {
            $now = now();
            $usage = $this->lemma->getMonthlyUsage($now->year, $now->month);
            return response()->json(['success' => true, 'data' => $usage]);
        } catch (Exception $e) {
            return response()->json(['success' => false, 'error' => $e->getMessage()], 500);
        }
    }
}

// ============================================================================
// WORDPRESS INTEGRATION
// ============================================================================

/**
 * WordPress Plugin Integration
 */
class WordPressLemmaIntegration
{
    private LemmaClient $lemma;

    public function __construct()
    {
        $this->lemma = new LemmaClient(get_option('lemma_api_key'));
        
        add_action('init', [$this, 'initHooks']);
        add_action('wp_enqueue_scripts', [$this, 'enqueueScripts']);
        add_action('wp_ajax_lemma_challenge', [$this, 'handleChallenge']);
        add_action('wp_ajax_nopriv_lemma_challenge', [$this, 'handleChallenge']);
        add_action('wp_ajax_lemma_verify', [$this, 'handleVerification']);
        add_action('wp_ajax_nopriv_lemma_verify', [$this, 'handleVerification']);
    }

    public function initHooks()
    {
        // Add admin menu for settings
        add_action('admin_menu', [$this, 'addAdminMenu']);
    }

    public function enqueueScripts()
    {
        wp_enqueue_script('lemma-integration', plugin_dir_url(__FILE__) . 'assets/lemma.js', ['jquery'], '1.0.0', true);
        wp_localize_script('lemma-integration', 'lemma_ajax', [
            'ajax_url' => admin_url('admin-ajax.php'),
            'nonce' => wp_create_nonce('lemma_nonce')
        ]);
    }

    public function handleChallenge()
    {
        check_ajax_referer('lemma_nonce', 'nonce');
        
        try {
            $challenge = $this->lemma->generateChallenge();
            wp_send_json_success($challenge);
        } catch (Exception $e) {
            wp_send_json_error($e->getMessage());
        }
    }

    public function handleVerification()
    {
        check_ajax_referer('lemma_nonce', 'nonce');
        
        try {
            $presentation = json_decode(stripslashes($_POST['presentation']), true);
            $challenge = sanitize_text_field($_POST['challenge']);
            $domain = sanitize_text_field($_POST['domain']) ?: get_site_url();

            $result = $this->lemma->verifyHuman($presentation, $challenge, $domain);

            if ($result['success'] && $result['data']['verified']) {
                $_SESSION['lemma_verified'] = true;
                $_SESSION['lemma_user_id'] = $result['data']['user_id'];
            }

            wp_send_json($result);
        } catch (Exception $e) {
            wp_send_json_error($e->getMessage());
        }
    }

    /**
     * Shortcode for protected content
     */
    public function protectedContentShortcode($atts, $content = '')
    {
        if (!isset($_SESSION['lemma_verified']) || !$_SESSION['lemma_verified']) {
            return '<div class="lemma-verification-required">
                <h3>Human Verification Required</h3>
                <p>This content is only accessible to verified humans.</p>
                <button class="lemma-verify-button">Verify with Lemma</button>
            </div>';
        }

        return $content;
    }
}

// ============================================================================
// TESTING UTILITIES
// ============================================================================

class LemmaTestSuite
{
    private LemmaClient $lemma;

    public function __construct()
    {
        $this->lemma = new LemmaClient(LEMMA_API_KEY);
    }

    /**
     * Run integration tests
     */
    public function runTests(): bool
    {
        echo "🧪 Testing Lemma Integration...\n";

        try {
            // Test health check
            $health = $this->lemma->healthCheck();
            echo "✅ Health check: " . $health['status'] . "\n";

            // Test challenge generation
            $challenge = $this->lemma->generateChallenge();
            echo "✅ Challenge generated: " . substr($challenge['challenge'], 0, 10) . "...\n";

            // Test usage metrics (if available)
            try {
                $usage = $this->lemma->getMonthlyUsage(date('Y'), date('n'));
                echo "✅ Usage metrics retrieved: " . ($usage['total_verifications'] ?? 0) . " verifications\n";
            } catch (Exception $e) {
                echo "ℹ️ Usage metrics not available (normal for new accounts)\n";
            }

            echo "🎉 All tests passed! Lemma integration is ready.\n";
            return true;

        } catch (Exception $e) {
            echo "❌ Integration test failed: " . $e->getMessage() . "\n";
            return false;
        }
    }
}

// ============================================================================
// SANDBOX UTILITIES
// ============================================================================

class LemmaSandbox
{
    private LemmaClient $lemma;

    public function __construct()
    {
        $this->lemma = new LemmaClient(LEMMA_API_KEY);
    }

    /**
     * Create a test credential for sandbox testing
     */
    public function createTestCredential(?string $userId = null): ?array
    {
        if (!$userId) {
            $userId = 'test_user_' . time();
        }

        try {
            return $this->lemma->issueCredential($userId, "sandbox");
        } catch (Exception $e) {
            error_log("Failed to create test credential: " . $e->getMessage());
            return null;
        }
    }

    /**
     * Simulate a complete verification flow for testing
     */
    public function simulateVerificationFlow(string $domain = "localhost"): bool
    {
        try {
            // Step 1: Generate challenge
            $challengeData = $this->lemma->generateChallenge();
            $challenge = $challengeData['challenge'];
            echo "Generated challenge: " . substr($challenge, 0, 10) . "...\n";

            // Step 2: Create test credential
            $credentialData = $this->createTestCredential();
            if (!$credentialData) {
                return false;
            }

            $credential = $credentialData['data']['credential'];
            echo "Created test credential for user: " . $credential['credentialSubject']['id'] . "\n";

            // Step 3: Simulate verification (would normally come from frontend)
            $presentation = [
                "@context" => ["https://www.w3.org/2018/credentials/v1"],
                "type" => ["VerifiablePresentation"],
                "verifiableCredential" => [$credential],
                "proof" => [
                    "type" => "Ed25519Signature2020",
                    "challenge" => $challenge,
                    "domain" => $domain
                ]
            ];

            // Step 4: Verify presentation
            $result = $this->lemma->verifyHuman($presentation, $challenge, $domain);

            if ($result['success'] && $result['data']['verified']) {
                echo "✅ Verification successful!\n";
                return true;
            } else {
                echo "❌ Verification failed!\n";
                return false;
            }

        } catch (Exception $e) {
            echo "❌ Simulation failed: " . $e->getMessage() . "\n";
            return false;
        }
    }
}

// ============================================================================
// EXAMPLE USAGE SCRIPTS
// ============================================================================

// Basic usage example
if (basename(__FILE__) === basename($_SERVER['SCRIPT_NAME'])) {
    // Parse command line arguments
    $options = getopt("", ["test", "sandbox", "serve:"]);

    if (isset($options['test'])) {
        $testSuite = new LemmaTestSuite();
        $testSuite->runTests();
    }

    if (isset($options['sandbox'])) {
        $sandbox = new LemmaSandbox();
        $sandbox->simulateVerificationFlow();
    }

    if (isset($options['serve'])) {
        $port = $options['serve'];
        echo "🚀 Starting PHP development server on port $port\n";
        echo "📖 Health check: http://localhost:$port/health.php\n";
        echo "🔒 Protected endpoint: http://localhost:$port/protected.php\n";
        
        // This would start a development server (requires PHP 5.4+)
        // exec("php -S localhost:$port -t " . __DIR__);
    }

    if (empty($options)) {
        echo "PHP Lemma Integration\n";
        echo "Usage: php " . basename(__FILE__) . " [options]\n";
        echo "  --test     Run integration tests\n";
        echo "  --sandbox  Run sandbox simulation\n";
        echo "  --serve=PORT  Start development server\n";
        
        // Run basic test
        $testSuite = new LemmaTestSuite();
        $testSuite->runTests();
    }
}

// ============================================================================
// CONFIGURATION FILES
// ============================================================================

/**
 * Laravel configuration file: config/lemma.php
 */
function getLaravelConfig(): array
{
    return [
        'api_key' => env('LEMMA_API_KEY'),
        'base_url' => env('LEMMA_BASE_URL', 'https://lemma.id'),
        'domain' => env('LEMMA_DOMAIN', 'localhost'),
        'session_key' => 'lemma_verified',
    ];
}

/**
 * WordPress plugin header
 */
function getWordPressPluginHeader(): string
{
    return '<?php
/*
Plugin Name: Lemma Human Verification
Description: Integrate Lemma human verification into your WordPress site
Version: 1.0.0
Author: Lemma Network
*/

// Prevent direct access
if (!defined("ABSPATH")) {
    exit;
}

require_once plugin_dir_path(__FILE__) . "lemma-integration.php";

// Initialize the plugin
add_action("plugins_loaded", function() {
    new WordPressLemmaIntegration();
});
';
}

?>

<!-- 
============================================================================
USAGE EXAMPLES
============================================================================

1. Basic PHP Usage:
   $lemma = new LemmaClient($_ENV['LEMMA_API_KEY']);
   $challenge = $lemma->generateChallenge();
   $result = $lemma->verifyHuman($presentation, $challenge['challenge'], 'yourdomain.com');

2. Vanilla PHP Integration:
   $integration = new VanillaPHPLemmaIntegration('yourdomain.com');
   if (!$integration->requireHuman()) {
       exit; // Not verified
   }
   // Serve protected content

3. Laravel Integration:
   Route::post('/api/protected', [Controller::class, 'method'])->middleware('lemma');

4. WordPress Integration:
   [lemma_protected]Your protected content here[/lemma_protected]

5. Testing:
   php php-integration.php --test --sandbox

6. Environment Variables:
   LEMMA_API_KEY=your_api_key_here

--> 