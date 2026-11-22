"""
ani_domain.py — chemical domain of the ANI potentials (torch-free).

Importing torch/torchani costs seconds and hundreds of MB, so everything that
only needs to *know* what ANI can handle (the web backend, the validators, the
unit tests) lives here and never imports them.

Domains (from the original publications / TorchANI):
    ANI-1x, ANI-1ccx : H, C, N, O
    ANI-2x           : H, C, N, O, F, S, Cl
All three were trained on *neutral, closed-shell* molecules.
"""

ANI_MODELS = {
    "ANI1x": {
        "elements": ("H", "C", "N", "O"),
        "label": "ANI-1x (wB97X/6-31G*)",
    },
    "ANI1ccx": {
        "elements": ("H", "C", "N", "O"),
        "label": "ANI-1ccx (CCSD(T)*/CBS transfer learning)",
    },
    "ANI2x": {
        "elements": ("H", "C", "N", "O", "F", "S", "Cl"),
        "label": "ANI-2x (wB97X/6-31G*, adds F, S, Cl)",
    },
}

_ATOMIC_NUMBERS = {
    "H": 1, "He": 2, "Li": 3, "Be": 4, "B": 5, "C": 6, "N": 7, "O": 8, "F": 9,
    "Ne": 10, "Na": 11, "Mg": 12, "Al": 13, "Si": 14, "P": 15, "S": 16,
    "Cl": 17, "Ar": 18, "K": 19, "Ca": 20, "Br": 35, "I": 53,
}


class DomainError(ValueError):
    """The molecule is outside the chemical domain of the requested model."""


def normalize_model_name(name):
    """'ani-1ccx', 'ANI1CCX', 'ani2x', 'auto', '' -> canonical key or 'auto'."""
    if name is None:
        return "auto"
    key = str(name).strip().lower().replace("-", "").replace("_", "").replace(" ", "")
    if key in ("", "auto", "automatic", "default"):
        return "auto"
    table = {k.lower(): k for k in ANI_MODELS}
    if key in table:
        return table[key]
    raise DomainError(
        "Unknown ANI model '%s'. Valid options: auto, %s." % (name, ", ".join(ANI_MODELS))
    )


def elements_of(symbols):
    seen = []
    for s in symbols:
        s = str(s).capitalize()
        if s not in seen:
            seen.append(s)
    return seen


def electron_count(symbols, charge=0):
    n = 0
    for s in symbols:
        s = str(s).capitalize()
        if s not in _ATOMIC_NUMBERS:
            raise DomainError("Unsupported element symbol '%s'." % s)
        n += _ATOMIC_NUMBERS[s]
    return n - int(charge)


def resolve_model(symbols, requested="auto", charge=0):
    """Pick the ANI model to use and validate the molecule against it.

    in:
        symbols   : iterable of element symbols (explicit hydrogens included)
        requested : 'auto' | 'ANI1x' | 'ANI1ccx' | 'ANI2x'
        charge    : total formal charge
    out:
        dict(model, notes[list of str], warnings[list of str])
    raises:
        DomainError if no ANI model can describe the molecule.
    """
    requested = normalize_model_name(requested)
    elems = elements_of(symbols)
    notes, warnings = [], []

    if electron_count(symbols, charge) % 2 == 1:
        raise DomainError(
            "Open-shell species (odd number of electrons). ANI potentials were "
            "trained on closed-shell molecules only."
        )
    if charge != 0:
        warnings.append(
            "Net charge %+d: ANI was trained on neutral molecules, so energies of "
            "ions/zwitterions are outside the training domain and not reliable." % charge
        )

    def unsupported(model):
        ok = set(ANI_MODELS[model]["elements"])
        return [e for e in elems if e not in ok]

    if requested == "auto":
        for candidate in ("ANI1ccx", "ANI2x"):
            if not unsupported(candidate):
                if candidate == "ANI2x":
                    notes.append(
                        "Contains %s: using ANI-2x (the only ANI model covering F, S, Cl)."
                        % ", ".join(e for e in elems if e in ("F", "S", "Cl"))
                    )
                return {"model": candidate, "notes": notes, "warnings": warnings}
        raise DomainError(
            "Elements outside the ANI domain: %s. Supported: H, C, N, O (ANI-1x/1ccx) "
            "plus F, S, Cl (ANI-2x)." % ", ".join(unsupported("ANI2x"))
        )

    bad = unsupported(requested)
    if not bad:
        return {"model": requested, "notes": notes, "warnings": warnings}

    if not unsupported("ANI2x"):
        notes.append(
            "%s does not support %s; switched automatically to ANI-2x."
            % (requested, ", ".join(bad))
        )
        return {"model": "ANI2x", "notes": notes, "warnings": warnings}

    raise DomainError(
        "Elements outside the ANI domain: %s. Supported: H, C, N, O (ANI-1x/1ccx) "
        "plus F, S, Cl (ANI-2x)."
        % ", ".join(sorted(set(unsupported("ANI2x")) | set(bad)))
    )
