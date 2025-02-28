"""Core module that contains all functions related to extracting out time
series data.
"""

import os
from itertools import repeat
import multiprocessing
import numpy as np
import pandas as pd
import nibabel as nib
from nilearn.image import load_img
from nilearn.input_data import NiftiMasker, NiftiLabelsMasker


def _discard_initial_scans(img, n_scans, regressors=None):
    """Remove first number of scans from functional image and regressors"""
    # crop scans from functional
    arr = img.get_data()
    arr = arr[:, :, :, n_scans:]
    out_img = nib.Nifti1Image(arr, img.affine)

    if regressors is not None:
        # crop from regressors
        out_reg = regressors[n_scans:, :]
    else:
        out_reg = None

    return out_img, out_reg


## CONFOUND REGRESSOR FUNCTIONS

def _compute_realign_derivs(regressors, t_r):
    """Compute derivatives from motion realignment parameters"""
    cols = [i for i in regressors.columns if ('rot' in i) | ('trans' in i)]
    realign = regressors[cols].values
    # compute central differences with sample distances = TR; (dx)
    derivs = np.gradient(realign, t_r, axis=0)
    deriv_cols = ['{}_d'.format(i) for i in cols]
    return pd.concat([regressors, pd.DataFrame(derivs, columns=deriv_cols)],
                     axis=1)


def _build_regressors(fname, regressor_names, realign_derivatives=False,
                      t_r=None):
    """Create regressors for masking"""
    all_regressors = pd.read_csv(fname, sep=r'\t', engine='python')
    regressors = all_regressors[regressor_names]
    if realign_derivatives:
        if t_r is not None:
            regressors = _compute_realign_derivs(regressors, t_r)
        else:
            raise ValueError('t_r not provided for realignment derivatives.')
    return regressors.values


## MASKING FUNCTIONS

def _set_masker(mask_img, **kwargs):
    """Check and see if multiple ROIs exist in atlas file"""
    n_rois = np.unique(mask_img.get_data())
    print('  {} region(s) detected from {}'.format(len(n_rois) - 1,
                                                   mask_img.get_filename()))

    if len(n_rois) > 2:
        masker = NiftiLabelsMasker(mask_img, **kwargs)
    elif len(n_rois) == 2:
        masker = NiftiMasker(mask_img, **kwargs)
    else:
        # only 1 value found
        raise ValueError('No ROI detected; check ROI file')
    return masker


def _mask(masker, img, confounds=None, roi_labels=None, as_voxels=False):
    """Extract timeseries from an image and apply post-processing"""
    timeseries = masker.fit_transform(img, confounds=confounds)

    if isinstance(masker, NiftiMasker):
        if as_voxels:
            labels = ['voxel{}'.format(i)
                      for i in np.arange(timeseries.shape[1])]
        else:
            timeseries = np.mean(timeseries, axis=1)
            labels = ['roi'] if roi_labels is None else roi_labels
    else:
        labels = masker.labels_ if roi_labels is None else roi_labels

    return pd.DataFrame(timeseries, columns=[str(i) for i in labels])


def _mask_and_save(masker, img_name, output_dir, regressor_file=None,
                   regressor_names=None, realign_derivs=False, t_r=None,
                   as_voxels=False, labels=None, discard_scans=None):
    """Runs the full masking process and saves output for a single image;
    the main function used by `make_timeseries` `make_timeseries`"""
    basename = os.path.basename(img_name)
    print('  Extracting from {}'.format(basename))
    img = nib.load(img_name)

    if regressor_file is not None:
        confounds = _build_regressors(regressor_file, regressor_names,
                                        realign_derivs, t_r)
    else:
        confounds = None

    if discard_scans is not None:
        if discard_scans > 0:
            img, confounds = _discard_initial_scans(img, discard_scans,
                                                    confounds)

    data = _mask(masker, img, confounds, labels, as_voxels)

    out_fname = basename.split('.')[0] + '_timeseries.tsv'
    data.to_csv(os.path.join(output_dir, out_fname), sep='\t', index=False,
                float_format='%.8f')


def make_timeseries(input_files, mask_img, output_dir, labels=None,
                    regressor_files=None, regressor_names=None,
                    realign_derivs=False, as_voxels=False, discard_scans=None,
                    n_jobs=1, **masker_kwargs):
    """Extract timeseries data from input files using an roi file to demark
    the region(s) of interest(s). This is the main function of this module.

    Parameters
    ----------
    input_files : list of niimg-like
        List of input NIfTI functional images
    roi_file : niimg-like
        Image that contains region mask(s). Can either be a single binary mask
        for a single region, or a numerically labeled atlas file. 0 must
        indicate background (non-region voxels).
    output_dir : str
        Save directory.
    labels : str or list of str
        ROI names which are in order of ascending numeric labels in roi_file.
        Default is None
    regressor_files : list of str, optional
        Confound .csv files for each run. Default is None
    regressors : list of str, optional
        Regressor names to select from `regressor_files` headers. Default is
        None
    realign_derivs : bool, optional
        Whether to compute and include the temporal derivative of any head
        motion realignment regressors produced from motion correction. This
        will automatically compute the derivative only for columns with 'rot'
        or 'trans' in them. Default is False.
    as_voxels : bool, optional
        Extract out individual voxel timecourses rather than mean timecourse of
        the ROI, by default False. NOTE: This is only available for binary masks,
        not for atlas images (yet)
    discard_scans : int, optional
        The number of scans to discard at the start of each functional image,
        prior to any sort of extraction and post-processing. This is prevents
        unstabilized signals at the start from being included in signal
        standardization, etc.
    n_jobs : int, optional
        Number of processes to use for extraction if parallelization is
        dersired. Default is 1 (no parallelization)
    **masker_kwargs
        Keyword arguments for `nilearn.input_data` Masker objects.
    """
    mask_img = load_img(mask_img)
    masker = _set_masker(mask_img, **masker_kwargs)

    # set as list of NoneType if no regressor files; makes it easy for
    # iterations
    if regressor_files is None:
        regressor_files = [regressor_files] * len(input_files)

    # no parallelization
    if n_jobs == 1:
        for i, img in enumerate(input_files):
            _mask_and_save(masker, img, output_dir, regressor_files[i],
                           regressor_names, realign_derivs, masker_kwargs['t_r'],
                           as_voxels, labels, discard_scans)
    else:
        # repeat parameters are held constant for all parallelized iterations
        args = zip(
            repeat(masker),
            input_files, # iterate over
            repeat(output_dir),
            regressor_files, # iterate over, paired with input_files
            repeat(regressor_names),
            repeat(realign_derivs),
            repeat(masker_kwargs['t_r']),
            repeat(as_voxels),
            repeat(labels),
            repeat(discard_scans)
        )
        with multiprocessing.Pool(processes=n_jobs) as pool:
            pool.starmap(_mask_and_save, args)

