import numpy as np

from aura.rag.projection import needs_refit, place, project


def test_place_is_dominated_by_the_most_similar_neighbour():
    xy = place([(0.95, (1.0, 1.0)), (0.70, (-1.0, -1.0)), (0.69, (-1.0, 1.0))])
    assert xy[0] > 0.95 and xy[1] > 0.95


def test_place_averages_equally_similar_neighbours():
    assert place([(0.8, (0.0, 0.0)), (0.8, (1.0, 1.0))]) == (0.5, 0.5)
    assert place([]) is None


def test_small_inputs_use_pca_scaled_to_unit_box():
    rng = np.random.default_rng(1)
    coords, method, trust = project(rng.normal(size=(8, 32)).astype(np.float32))
    assert method == "pca" and trust is None
    assert coords.shape == (8, 2) and np.abs(coords).max() <= 1.0 + 1e-9


def test_umap_keeps_clusters_apart_with_high_trustworthiness():
    rng = np.random.default_rng(42)
    centres = rng.normal(size=(3, 64)) * 5
    x = np.vstack([c + rng.normal(size=(20, 64)) for c in centres]).astype(np.float32)
    coords, method, trust = project(x)
    assert method == "umap" and trust is not None and trust > 0.85
    mean = [coords[i * 20 : (i + 1) * 20].mean(axis=0) for i in range(3)]
    spread = max(np.linalg.norm(coords[i * 20 : (i + 1) * 20] - mean[i], axis=1).mean() for i in range(3))
    gap = min(np.linalg.norm(mean[i] - mean[j]) for i in range(3) for j in range(i + 1, 3))
    assert gap > 2 * spread


def test_refit_policy():
    assert needs_refit(0, 10) and needs_refit(70, 100) and not needs_refit(85, 100) and not needs_refit(0, 0)
