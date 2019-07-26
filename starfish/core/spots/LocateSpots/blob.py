from functools import partial
from typing import Optional, Union

import numpy as np
import pandas as pd
import xarray as xr
from skimage.feature import blob_dog, blob_doh, blob_log

from starfish.core.imagestack.imagestack import ImageStack
from starfish.core.intensity_table.intensity_table import IntensityTable
from starfish.core.types import Axes, Features, Number, SpotAttributes
from ._base import LocateSpotsAlgorithmBase

blob_detectors = {
    'blob_dog': blob_dog,
    'blob_doh': blob_doh,
    'blob_log': blob_log
}


class BlobDetector(LocateSpotsAlgorithmBase):
    """
    Multi-dimensional gaussian spot detector

    This method is a wrapper for skimage.feature.blob_log

    Parameters
    ----------
    min_sigma : float
        The minimum standard deviation for Gaussian Kernel. Keep this low to
        detect smaller blobs.
    max_sigma : float
        The maximum standard deviation for Gaussian Kernel. Keep this high to
        detect larger blobs.
    num_sigma : int
        The number of intermediate values of standard deviations to consider
        between `min_sigma` and `max_sigma`.
    threshold : float
        The absolute lower bound for scale space maxima. Local maxima smaller
        than thresh are ignored. Reduce this to detect blobs with less
        intensities.
    overlap : float [0, 1]
        If two spots have more than this fraction of overlap, the spots are combined
        (default = 0.5)
    measurement_type : str ['max', 'mean']
        name of the function used to calculate the intensity for each identified spot area
    detector_method: str ['blob_dog', 'blob_doh', 'blob_log']
        name of the type of detection method used from skimage.feature, default: blob_log

    Notes
    -----
    see also: http://scikit-image.org/docs/dev/auto_examples/features_detection/plot_blob.html

    """

    def __init__(
            self,
            min_sigma: Number,
            max_sigma: Number,
            num_sigma: int,
            threshold: Number,
            overlap: float = 0.5,
            measurement_type='max',
            is_volume: bool = True,
            detector_method: str = 'blob_log'
    ) -> None:

        self.min_sigma = min_sigma
        self.max_sigma = max_sigma
        self.num_sigma = num_sigma
        self.threshold = threshold
        self.overlap = overlap
        self.is_volume = is_volume
        self.measurement_function = self._get_measurement_function(measurement_type)
        try:
            self.detector_method = blob_detectors[detector_method]
        except ValueError:
            raise ValueError("Detector method must be one of {blob_log, blob_dog, blob_doh}")

    def image_to_spots(self, data_image: Union[np.ndarray, xr.DataArray]) -> SpotAttributes:
        """
        Find spots using a gaussian blob finding algorithm

        Parameters
        ----------
        data_image : Union[np.ndarray, xr.DataArray]
            image containing spots to be detected

        Returns
        -------
        SpotAttributes :
            DataFrame of metadata containing the coordinates, intensity and radius of each spot

        """

        fitted_blobs_array: np.ndarray = self.detector_method(
            data_image,
            self.min_sigma,
            self.max_sigma,
            self.num_sigma,
            self.threshold,
            self.overlap
        )

        if fitted_blobs_array.shape[0] == 0:
            return SpotAttributes.empty(extra_fields=['intensity', 'spot_id'])

        # create the SpotAttributes Table
        columns = [Axes.ZPLANE.value, Axes.Y.value, Axes.X.value, Features.SPOT_RADIUS]
        fitted_blobs = pd.DataFrame(data=fitted_blobs_array, columns=columns)

        # convert standard deviation of gaussian kernel used to identify spot to radius of spot
        converted_radius = np.round(fitted_blobs[Features.SPOT_RADIUS] * np.sqrt(3))
        fitted_blobs[Features.SPOT_RADIUS] = converted_radius

        # convert the array to int so it can be used to index
        spots = SpotAttributes(fitted_blobs)
        spots.data['spot_id'] = np.arange(spots.data.shape[0])

        return spots

    def run(
            self,
            image_stack: ImageStack,
            n_processes: Optional[int] = None,
            *args,
    ) -> SpotAttributes:
        """
        Find spots.

        Parameters
        ----------
        primary_image : ImageStack
            ImageStack where we find the spots in.
        blobs_image : Optional[ImageStack]
            If provided, spots will be found in the blobs image, and intensities will be measured
            across rounds and channels. Otherwise, spots are measured independently for each channel
            and round.
        blobs_axes : Optional[Tuple[Axes, ...]]
            If blobs_image is provided, blobs_axes must be provided as well.  blobs_axes represents
            the axes across which the blobs image is max projected before spot detection is done.
        n_processes : Optional[int] = None,
            Number of processes to devote to spot finding.
        """

        spot_finding_method = partial(self.image_to_spots, *args)
        spot_attributes_list = image_stack.transform(
            func=spot_finding_method,
            group_by={Axes.ROUND, Axes.CH},
            n_processes=n_processes
        )

        return SpotAttributes(pd.concat([sa.data for sa, inds in spot_attributes_list], sort=True))

