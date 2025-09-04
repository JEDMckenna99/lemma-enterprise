(** Simple test to verify basic Coq syntax and logic *)

(** Basic arithmetic proof *)
Theorem simple_arithmetic : forall n : nat, n + 0 = n.
Proof.
  intros n.
  rewrite Nat.add_0_r.
  reflexivity.
Qed.

(** Basic logical proof *)
Theorem simple_logic : forall P Q : Prop, P -> (P -> Q) -> Q.
Proof.
  intros P Q H_P H_impl.
  apply H_impl.
  exact H_P.
Qed.

(** Test that our basic types make sense *)
Definition Microseconds := nat.
Definition MAX_TIME : Microseconds := 4176.

Theorem max_time_positive : MAX_TIME > 0.
Proof.
  unfold MAX_TIME.
  omega.
Qed.

Print "✅ Basic proofs work - Coq syntax is valid!".
