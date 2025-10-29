/* tslint:disable */
/* eslint-disable */
/**
 * Verify Ed25519 signature (raw bytes)
 * 
 * Parameters:
 * - public_key: 32-byte Ed25519 public key
 * - message: Message bytes (already hashed to 32 bytes by createVerificationMessage)
 * - signature: 64-byte Ed25519 signature
 * 
 * Returns: true if signature is valid
 */
export function verify_signature_bytes(public_key: Uint8Array, message: Uint8Array, signature: Uint8Array): boolean;
/**
 * Create verification message from credential (for debugging)
 * 
 * This duplicates the JavaScript createVerificationMessage logic
 * to ensure both produce identical output.
 */
export function create_verification_message_debug(id: string, issuer: string, subject: string, issued_at: bigint, expires_at: bigint | null | undefined, claims_json: string): Uint8Array;
/**
 * Initialize WASM module
 */
export function init_wasm(): void;

export type InitInput = RequestInfo | URL | Response | BufferSource | WebAssembly.Module;

export interface InitOutput {
  readonly memory: WebAssembly.Memory;
  readonly verify_signature_bytes: (a: number, b: number, c: number, d: number, e: number, f: number) => number;
  readonly create_verification_message_debug: (a: number, b: number, c: number, d: number, e: number, f: number, g: bigint, h: number, i: bigint, j: number, k: number) => [number, number];
  readonly init_wasm: () => void;
  readonly __wbindgen_free: (a: number, b: number, c: number) => void;
  readonly __wbindgen_malloc: (a: number, b: number) => number;
  readonly __wbindgen_realloc: (a: number, b: number, c: number, d: number) => number;
  readonly __wbindgen_export_3: WebAssembly.Table;
  readonly __wbindgen_start: () => void;
}

export type SyncInitInput = BufferSource | WebAssembly.Module;
/**
* Instantiates the given `module`, which can either be bytes or
* a precompiled `WebAssembly.Module`.
*
* @param {{ module: SyncInitInput }} module - Passing `SyncInitInput` directly is deprecated.
*
* @returns {InitOutput}
*/
export function initSync(module: { module: SyncInitInput } | SyncInitInput): InitOutput;

/**
* If `module_or_path` is {RequestInfo} or {URL}, makes a request and
* for everything else, calls `WebAssembly.instantiate` directly.
*
* @param {{ module_or_path: InitInput | Promise<InitInput> }} module_or_path - Passing `InitInput` directly is deprecated.
*
* @returns {Promise<InitOutput>}
*/
export default function __wbg_init (module_or_path?: { module_or_path: InitInput | Promise<InitInput> } | InitInput | Promise<InitInput>): Promise<InitOutput>;
