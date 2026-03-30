import {
  createLemmaAuth,
  LemmaAuthOptions,
  LemmaErrorPayload,
  LemmaRequestLike,
  LemmaResponseLike,
} from "../../sdk/node/lemma-auth-express";

const options: LemmaAuthOptions = {
  requiredSite: "example.com",
  verifyCredential: async (_credential) => ({ valid: true }),
};

const lemma = createLemmaAuth(options);

const req: LemmaRequestLike = {
  header: (_name: string) => undefined,
};

const res: LemmaResponseLike = {
  status: (_code: number) => res,
  json: (_body: unknown) => undefined,
};

const middleware = lemma.attachPrincipal();
middleware(req, res, () => undefined);

const guarded = lemma.requireLemma({ scope: "read", siteBound: true });
guarded(req, res, () => undefined);

const denied: LemmaErrorPayload = {
  success: false,
  error: "missing_scope",
  message: "Insufficient scope",
};

void denied;
