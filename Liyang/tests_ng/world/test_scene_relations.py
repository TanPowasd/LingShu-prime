# -*- coding: utf-8 -*-
"""scene_relations：关系违反判定与求解（left_of/right_of 修正）；compat 派生 scene_model。"""
import itertools
import os
import subprocess
import sys
from dataclasses import dataclass, field

import pytest

from lingshu_ng.world import scene_relations as R

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@dataclass
class E:
    pos: tuple
    relations: list = field(default_factory=list)


def _holds(kind, a, b):
    return not R.violated(kind, a, b)


@pytest.mark.parametrize("kind", R.RELATION_KINDS)
@pytest.mark.parametrize("dx,dz", list(itertools.product([-2.5, -0.5, 0.0, 0.5, 2.5], repeat=2)))
def test_fix_satisfies_and_satisfied_is_untouched(kind, dx, dz):
    t = (10.0, 0.45, 5.0)
    a = (10.0 + dx, 0.45, 5.0 + dz)
    w = {"a": E(a, [("t", kind)]), "t": E(t)}
    n = R.solve_relations(w)
    assert _holds(kind, w["a"].pos, t)
    assert w["a"].pos[1] == 0.45
    if _holds(kind, a, t):
        assert n == 0 and w["a"].pos == a


def test_left_right_semantics():
    t = (0.0, 0.0, 0.0)
    assert R.violated("left_of", (0.5, 0, 0), t) and not R.violated("left_of", (-0.5, 0, 0), t)
    assert R.violated("right_of", (-0.5, 0, 0), t) and not R.violated("right_of", (0.5, 0, 0), t)
    assert R.violated("left_of", t, t) and R.violated("right_of", t, t)
    assert not R.violated("unknown_kind", t, t)


def test_unknown_target_and_chain():
    w = {"a": E((5.0, 0, 0), [("b", "left_of"), ("ghost", "near")]), "b": E((0.0, 0, 0), [("c", "right_of")]),
         "c": E((3.0, 0, 0))}
    R.solve_relations(w)
    assert w["b"].pos[0] > w["c"].pos[0]
    assert w["a"].pos[0] < w["b"].pos[0]


def test_compat_scene_model_uses_fixed_solver():
    code = ("import sys; sys.path.insert(0, %r)\n"
            "from lingshu_ng.world.compat import install_legacy_aliases\n"
            "assert 'scene_model' in install_legacy_aliases()\n"
            "from lingshu.world.scene_model import WorldModel, PRESENT_BY_CATEGORY\n"
            "from lingshu.world.world3d import World3D\n"
            "import lingshu.world.scene_model as sm\n"
            "assert sm.World3D is World3D and PRESENT_BY_CATEGORY['chair'] == 'box'\n"
            "wm = WorldModel(); wm.add_entity('c','chair',(11,0.45,5)); wm.add_entity('t','table',(10,0.45,5))\n"
            "wm.relation('c','left_of','t').build()\n"
            "assert wm.entities['c'].pos[0] < 10, wm.entities['c'].pos\n"
            "wm2 = WorldModel(); wm2.add_entity('c','chair',(8,0.45,5)); wm2.add_entity('t','table',(10,0.45,5))\n"
            "wm2.relation('c','left_of','t').build()\n"
            "assert wm2.entities['c'].pos == (8,0.45,5)\n"
            "print('ok')\n" % REPO)
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
