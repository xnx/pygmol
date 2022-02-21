from itertools import combinations
import inspect

import numpy as np

from pygmol.model import Model
from pygmol.equations import ElectronEnergyEquations
from pytest import fixture
from numpy import ndarray

from .resources.example_chemistry import ExampleChemistry
from .resources.example_plasma_parameters import ExamplePlasmaParameters
from .resources.example_solutions import solutions


@fixture
def chemistry():
    return ExampleChemistry()


@fixture
def plasma_params():
    return ExamplePlasmaParameters()


def solutions_match(sol1: ndarray, sol2: ndarray) -> bool:
    zero_eff = 1.0e2
    # filtering out effectively zero densities...
    print(sol1[sol1 > zero_eff])
    print(sol2[sol1 > zero_eff])
    return np.isclose(sol1[sol1 > zero_eff], sol2[sol1 > zero_eff], rtol=5.0e-4).all()


def solution_expected(model: Model, test_case: str) -> bool:
    return solutions_match(model.solution_primary[-1], solutions.loc[test_case].values)


# noinspection PyProtectedMember
def run(model):
    model._initialize_equations()
    model._solve()
    model._build_solution()


def test_all_example_solutions_unique():
    for sol1, sol2 in combinations(solutions.values, 2):
        assert not solutions_match(sol1, sol2)


def test_nominal_solution(chemistry, plasma_params):
    model = Model(chemistry, plasma_params)
    run(model)
    assert solution_expected(model, "nominal")


def test_solution_feeds(chemistry, plasma_params):
    plasma_params.feeds = {"Ar": 100, "O": 100}
    model = Model(chemistry, plasma_params)
    run(model)
    assert solution_expected(model, "feeds")


def test_solution_sticking1(chemistry, plasma_params, monkeypatch):
    plasma_params.feeds = {"Ar": 100, "O": 100}
    # set sticking coefficients for all the ions and excited species to 1.0:
    chemistry.species_surface_sticking_coefficients = [
        1.0 if sp_id[-1] in "+-*" else 0.0 for sp_id in chemistry.species_ids
    ]
    model = Model(chemistry, plasma_params)
    monkeypatch.setattr(ElectronEnergyEquations, "diffusion_model", 0)
    run(model)
    assert solution_expected(model, "sticking1")


def test_solution_sticking2(chemistry, plasma_params, monkeypatch):
    plasma_params.feeds = {"Ar": 100, "O": 100}
    # set sticking coefficients for all the ions and excited species to 1.0:
    chemistry.species_surface_sticking_coefficients = [
        0.5 if sp_id[-1] in "+-*" else 0.0 for sp_id in chemistry.species_ids
    ]
    model = Model(chemistry, plasma_params)
    monkeypatch.setattr(ElectronEnergyEquations, "diffusion_model", 0)
    run(model)
    assert solution_expected(model, "sticking2")


def test_solution_return1(chemistry, plasma_params, monkeypatch):
    plasma_params.feeds = {"Ar": 100, "O": 100}
    stuck_species = [sp_id for sp_id in chemistry.species_ids if sp_id[-1] in "+-*"]
    stuck_species_indices = [
        chemistry.species_ids.index(sp_id) for sp_id in stuck_species
    ]
    chemistry.species_surface_sticking_coefficients = [
        0.5 if sp_id in stuck_species else 0.0 for sp_id in chemistry.species_ids
    ]
    for stuck_sp, stuck_sp_i in zip(stuck_species, stuck_species_indices):
        ret_sp = stuck_sp.rstrip("+-*")
        ret_sp_i = chemistry.species_ids.index(ret_sp)
        chemistry.species_surface_return_matrix[ret_sp_i][stuck_sp_i] = 1.0
    model = Model(chemistry, plasma_params)
    monkeypatch.setattr(ElectronEnergyEquations, "diffusion_model", 0)
    run(model)
    assert solution_expected(model, "return1")


def test_solution_return2(chemistry, plasma_params, monkeypatch):
    plasma_params.feeds = {"Ar": 100, "O": 100}
    stick_coefs = {"O-": 1, "O--": 1, "Ar+": 1, "Ar++": 1, "Ar*": 1, "Ar**": 1}
    chemistry.species_surface_sticking_coefficients = [
        stick_coefs.get(sp_id, 0) for sp_id in chemistry.species_ids
    ]
    ret_coefs = {
        "Ar+": {"Ar": 0.4, "Ar*": 0.3, "Ar**": 0.3},
        "Ar++": {"Ar": 3.0},
        "O-": {"O--": 0.5, "O": 0.5},
        "O--": {"O-": 0.1, "O": 0.9},
        "Ar*": {"Ar": 0.5},
        "Ar**": {"Ar*": 0.1, "Ar+": 0.1, "Ar": 0.8},
    }
    for stick_sp in stick_coefs:
        stick_i = chemistry.species_ids.index(stick_sp)
        for ret_sp in ret_coefs[stick_sp]:
            ret_i = chemistry.species_ids.index(ret_sp)
            chemistry.species_surface_return_matrix[ret_i][stick_i] = ret_coefs[
                stick_sp
            ][ret_sp]
    model = Model(chemistry, plasma_params)
    monkeypatch.setattr(ElectronEnergyEquations, "diffusion_model", 0)
    run(model)
    assert solution_expected(model, "return2")


def test_solution_reduced_reactions(chemistry, plasma_params, monkeypatch):
    removed_reactions_ids = {3, 4, 12}
    mask = [r_id not in removed_reactions_ids for r_id in chemistry.reactions_ids]
    for attr, val in inspect.getmembers(chemistry):
        if attr.startswith("reactions_"):
            setattr(chemistry, attr, list(np.array(val)[mask]))
    model = Model(chemistry, plasma_params)
    run(model)
    assert solution_expected(model, "reduced_reactions")


def test_solution_adhoc_k(chemistry, plasma_params, monkeypatch):
    increase_k = {10, 20, 30}
    for i, r_id in enumerate(chemistry.reactions_ids):
        if r_id in increase_k:
            chemistry.reactions_arrh_a[i] *= 1.1
    model = Model(chemistry, plasma_params)
    run(model)
    assert solution_expected(model, "adhoc_k")
