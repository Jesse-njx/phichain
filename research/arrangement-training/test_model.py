import unittest
import numpy as np
import torch
from masked_model import ArrangementTransformer, batch, encode_window, generate


def window():
    return dict(bpm=120, difficulty=14, notes=[dict(id=str(i),time=i*.25,type=1,duration=0,x=.2 if i%2 else .8) for i in range(16)])


class ModelTests(unittest.TestCase):
    def test_masked_input_has_no_target_leak(self):
        a = window(); b = window()
        for n in b['notes']:
            n['x'] = 1-n['x']
        ba = batch([a],np.random.default_rng(1),'cpu',mode='full')
        bb = batch([b],np.random.default_rng(1),'cpu',mode='full')
        for i in (0,1,2,4,5):
            self.assertTrue(torch.equal(ba[i],bb[i]))
        self.assertFalse(torch.equal(ba[3],bb[3]))

    def test_mirror_and_padding(self):
        a = window(); f,k,x = encode_window(a); mf,mk,mx = encode_window(a,mirror=True)
        np.testing.assert_array_equal(f,mf); np.testing.assert_array_equal(k,mk)
        np.testing.assert_array_equal(x+mx,np.full(16,127))
        b = dict(a, notes=a['notes'][:8])
        *_,mask,valid = batch([a,b],np.random.default_rng(1),'cpu',mode='full')
        self.assertEqual(valid.sum().item(),24)
        self.assertTrue(torch.equal(mask,valid))

    def test_mps_forward_backward_and_locked_generation(self):
        self.assertTrue(torch.backends.mps.is_available())
        model=ArrangementTransformer().to('mps')
        f,k,x,target,mask,valid=batch([window()],np.random.default_rng(0),'mps',mode='full')
        loss=torch.nn.functional.cross_entropy(model(f,k,x,valid)[mask],target[mask])
        loss.backward(); torch.mps.synchronize()
        self.assertTrue(torch.isfinite(loss).item())
        result=generate(model,window(),'mps',seed=1,steps=4,locked={0:.5})
        self.assertAlmostEqual(result[0],round(.5*127)/127)
        self.assertTrue(np.all((result>=0)&(result<=1)))


if __name__=='__main__':
    unittest.main()
