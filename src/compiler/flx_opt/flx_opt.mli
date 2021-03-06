(** Perform high level optimizations across the entire program. *)
val optimize_bsym_table :
  Flx_mtypes2.sym_state_t ->  (** The felix state. *)
  Flx_bsym_table.t ->         (** The bound symbol table. *)
  Flx_types.bid_t option ->          (** The root procedure. *)
  Flx_bsym_table.t

