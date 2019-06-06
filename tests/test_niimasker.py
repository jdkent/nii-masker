
import os
import pytest
import nibabel as nib
from nilearn.datasets import fetch_atlas_aal

from niimasker import niimasker


## HELPERS

def _get_atlas():
    """Fetch small atlas for testing purposes"""
    # save to path in test directory to only download atlas once
    test_path = os.path.dirname(__file__)
    data_dir = os.path.join(test_path, 'data-dir')
    os.makedirs(data_dir, exist_ok=True)
    return fetch_atlas_aal(data_dir=data_dir)


@pytest.fixture
def atlas_data():
    """Create a 4D image that repeats the atlas over 10 volumes.

    Every voxel/ROI is the same value across time. Therefore we can test if
    proper values are extracted (and if they are in the proper order).
    """

    atlas = _get_atlas()
    img = nib.load(atlas['maps'])
    return nib.concat_images([img] * 10)


@pytest.fixture
def regressors(tmpdir):
    pass


@pytest.fixture
def post_processed_data():
    """A post-processed version of the atlas_data, which is generated directly
    by nilearn rather than niimasker. The results from niimasker should
    directly match what is produced by nilearn.
    """
    pass


## TESTS


def test_discard_initial_scans(atlas_data):
    """Check if the correct number of scans are discarded at the start of the
    image
    """
    n_scans = 3
    img, regs = niimasker._discard_initial_scans(atlas_data, n_scans)
    assert img.get_data().shape[3] == atlas_data.get_data().shape[3] - n_scans
    assert regs is None


def test_set_masker(atlas_data):
    pass


def test_mask(atlas_data):
    pass


def test_mask_and_save(atlas_data, tmpdir):
    pass









