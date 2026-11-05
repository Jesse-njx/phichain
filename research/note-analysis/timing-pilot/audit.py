"""Post-run audit, chance-density control and song-level uncertainty.

No training, checkpoint selection or retuning is performed here.
"""
import json
import numpy as np
import run


def main():
    result = json.loads((run.OUT/'results.json').read_text())
    data = json.loads((run.OUT/'dataset.json').read_text())
    protocol = json.loads((run.OUT/'protocol.json').read_text())
    assert protocol['script_sha256'] == run.sha(run.Path(run.__file__))
    assert len({r['id'] for r in data}) == len(data)
    assert len({r['audio_sha256'] for r in data}) == len(data)
    assert run.matched(np.array([1., 1.01]), np.array([1.005]), .02) == 1
    assert run.matched(np.array([1.]), np.array([1.03]), .02) == 0
    assert all(r['excluded_outside'] == 0 for r in data)
    for m in result['models']:
        assert m['inference_repeat_max_score_difference'] == 0
        for budget in run.BUDGETS:
            base = result['baseline']['test'][str(budget)]['songs']
            trained = m['test'][str(budget)]['songs']
            assert [(x['id'],x['candidate_count']) for x in base] == [(x['id'],x['candidate_count']) for x in trained]
    rng = np.random.default_rng(20261102)
    chance, songs = [], []
    for row in data:
        if row['split'] != 'test': continue
        x, _, duration = run.features(row)
        ref = run.references(row)
        songs.append(dict(row=row, x=x, duration=duration, reference=ref))
        chance.append(rng.standard_normal(len(x)))
    differences = {}
    for budget in run.BUDGETS:
        per = result['baseline']['test'][str(budget)]['songs']
        differences[str(budget)] = {}
        for tol in ['10', '20', '35', '50']:
            base = np.array([r['coverage'][tol] for r in per])
            models = np.array([[r['coverage'][tol] for r in m['test'][str(budget)]['songs']] for m in result['models']])
            # Averaging run metrics is not an ensemble of model predictions.
            delta = models.mean(axis=0)-base
            bootstrap = delta[rng.integers(0, len(delta), (10000, len(delta)))].mean(axis=1)
            differences[str(budget)][tol] = dict(mean_percentage_points=float(100*delta.mean()),
                song_bootstrap_95_percentile_interval_pp=(100*np.percentile(bootstrap,[2.5,97.5])).tolist(),
                songs_improved=int(np.sum(delta>0)), songs_total=len(delta))
    audit = dict(checks='Passed: source hash, song/audio split uniqueness, one-to-one matching, in-duration labels, identical candidate counts, repeated inference.',
        random_score_density_control=run.report(songs, chance, 0),
        mean_of_two_training_runs_minus_baseline=differences,
        uncertainty_caveat='Bootstrap over only eight test songs, conditional on these two fitted models. Not population confidence; not adjusted for multiple comparisons.',
        not_tested=['Acoustic precision', 'Complete event recall', 'Instrument attribution', 'Musical intensity', 'Climax', 'Gain/encoding/chunk invariance', 'Human listening quality'])
    run.save('audit.json',audit)
    print(json.dumps(dict(difference_at_8_per_second=differences['8'],
        random_at_8_per_second=audit['random_score_density_control']['8']['macro_coverage']),indent=2))


if __name__ == '__main__': main()
