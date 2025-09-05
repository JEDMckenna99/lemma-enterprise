(** Simple test of our foundational types *)
Require Import Coq.Lists.List.
Require Import Coq.Arith.Arith.
Require Import Coq.Strings.String.
Require Import Coq.QArith.QArith.
Require Import Lia.
Import ListNotations.

(** Basic Types *)
Definition SecurityParameter := nat.
Definition Microseconds := nat.
Definition Credential := string.

(** Simple verification result *)
Inductive VerificationResult : Type :=
  | Verified : forall (confidence: Q) (time_us: Microseconds) (metadata: list (string * string)), VerificationResult
  | Failed : forall (reason: string) (time_us: Microseconds), VerificationResult.

(** Constants *)
Definition SECURITY_PARAMETER : SecurityParameter := (128%nat).
Definition MAX_VERIFICATION_TIME : Microseconds := (4176%nat).

(** Basic theorem *)
Theorem timing_bound_positive : (MAX_VERIFICATION_TIME > 0)%nat.
Proof.
  unfold MAX_VERIFICATION_TIME.
  lia.
Qed.

(** Verification results have timing *)
Theorem verification_has_timing :
  forall (vr : VerificationResult),
  match vr with
  | Verified _ time _ => (time >= 0)%nat
  | Failed _ time => (time >= 0)%nat
  end.
Proof.
  intros vr.
  destruct vr as [conf time meta | reason time]; lia.
Qed.

(** Simple foundations test passed! *)
