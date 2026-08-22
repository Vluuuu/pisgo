"""Deterministic color, spatial, edge, and texture features for banana images."""

from __future__ import annotations

import io
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import BinaryIO

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError
from sklearn.base import BaseEstimator, TransformerMixin


class CVFeatureError(ValueError):
    """Raised when an image cannot be converted to model features."""


@dataclass(frozen=True)
class ImageFeatureConfig:
    resize_width: int = 192
    resize_height: int = 128
    histogram_bins: int = 16
    grid_rows: int = 3
    grid_columns: int = 3

    def validate(self) -> None:
        if self.resize_width < 32 or self.resize_height < 32:
            raise CVFeatureError("Resize dimensions must be at least 32 pixels")
        if self.histogram_bins < 4:
            raise CVFeatureError("histogram_bins must be at least 4")
        if self.grid_rows < 1 or self.grid_columns < 1:
            raise CVFeatureError("Grid dimensions must be positive")

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


class BananaImageFeatureExtractor(BaseEstimator, TransformerMixin):
    """Scikit-learn compatible extractor accepting image bytes or filesystem paths."""

    def __init__(
        self,
        resize_width: int = 192,
        resize_height: int = 128,
        histogram_bins: int = 16,
        grid_rows: int = 3,
        grid_columns: int = 3,
    ) -> None:
        self.resize_width = resize_width
        self.resize_height = resize_height
        self.histogram_bins = histogram_bins
        self.grid_rows = grid_rows
        self.grid_columns = grid_columns

    @property
    def config(self) -> ImageFeatureConfig:
        config = ImageFeatureConfig(
            resize_width=self.resize_width,
            resize_height=self.resize_height,
            histogram_bins=self.histogram_bins,
            grid_rows=self.grid_rows,
            grid_columns=self.grid_columns,
        )
        config.validate()
        return config

    def fit(self, X: object, y: object = None) -> "BananaImageFeatureExtractor":
        self.config.validate()
        return self

    def transform(self, X: object) -> np.ndarray:
        return np.vstack([self.extract(item) for item in X])

    def extract(self, source: str | Path | bytes | bytearray | BinaryIO | Image.Image) -> np.ndarray:
        image = load_rgb_image(source, self.config)
        return extract_image_features(image, self.config)

    def get_feature_names_out(self, input_features: object = None) -> np.ndarray:
        return np.asarray(feature_names(self.config), dtype=object)


def load_rgb_image(
    source: str | Path | bytes | bytearray | BinaryIO | Image.Image,
    config: ImageFeatureConfig,
) -> Image.Image:
    config.validate()
    try:
        if isinstance(source, Image.Image):
            image = source.copy()
        elif isinstance(source, (bytes, bytearray)):
            image = Image.open(io.BytesIO(source))
        else:
            image = Image.open(source)
        image = ImageOps.exif_transpose(image).convert("RGB")
        image.load()
    except (OSError, ValueError, UnidentifiedImageError) as error:
        raise CVFeatureError(f"Unable to decode image: {error}") from error
    return image.resize((config.resize_width, config.resize_height), Image.Resampling.BILINEAR)


def _channel_histogram(values: np.ndarray, bins: int, value_range: tuple[float, float]) -> np.ndarray:
    histogram, _ = np.histogram(values, bins=bins, range=value_range)
    total = histogram.sum()
    return histogram.astype(np.float32) / max(total, 1)


def _channel_summary(values: np.ndarray) -> list[float]:
    return [
        float(np.mean(values)),
        float(np.std(values)),
        float(np.percentile(values, 10)),
        float(np.percentile(values, 50)),
        float(np.percentile(values, 90)),
    ]


def extract_image_features(image: Image.Image, config: ImageFeatureConfig) -> np.ndarray:
    rgb = np.asarray(image, dtype=np.float32) / 255.0
    hsv = np.asarray(image.convert("HSV"), dtype=np.float32) / 255.0
    grayscale = np.asarray(image.convert("L"), dtype=np.float32) / 255.0

    features: list[float] = []
    for array in (rgb, hsv):
        for channel in range(3):
            values = array[..., channel]
            features.extend(_channel_histogram(values, config.histogram_bins, (0.0, 1.0)))
            features.extend(_channel_summary(values))

    row_edges = np.linspace(0, rgb.shape[0], config.grid_rows + 1, dtype=int)
    column_edges = np.linspace(0, rgb.shape[1], config.grid_columns + 1, dtype=int)
    for row in range(config.grid_rows):
        for column in range(config.grid_columns):
            tile_rgb = rgb[row_edges[row] : row_edges[row + 1], column_edges[column] : column_edges[column + 1]]
            tile_hsv = hsv[row_edges[row] : row_edges[row + 1], column_edges[column] : column_edges[column + 1]]
            features.extend(np.mean(tile_rgb, axis=(0, 1)).tolist())
            features.extend(np.std(tile_rgb, axis=(0, 1)).tolist())
            features.extend(np.mean(tile_hsv, axis=(0, 1)).tolist())

    horizontal = np.abs(np.diff(grayscale, axis=1))
    vertical = np.abs(np.diff(grayscale, axis=0))
    features.extend(
        [
            float(horizontal.mean()),
            float(horizontal.std()),
            float(vertical.mean()),
            float(vertical.std()),
            float((horizontal > 0.08).mean()),
            float((vertical > 0.08).mean()),
        ]
    )

    saturation = hsv[..., 1]
    brightness = hsv[..., 2]
    features.extend(
        [
            float((saturation > 0.25).mean()),
            float((brightness < 0.25).mean()),
            float(((saturation > 0.25) & (brightness > 0.25)).mean()),
        ]
    )
    return np.asarray(features, dtype=np.float32)


def feature_names(config: ImageFeatureConfig) -> list[str]:
    names: list[str] = []
    for space in ("rgb", "hsv"):
        for channel in range(3):
            names.extend(f"{space}_{channel}_hist_{index}" for index in range(config.histogram_bins))
            names.extend(f"{space}_{channel}_{stat}" for stat in ("mean", "std", "p10", "p50", "p90"))
    for row in range(config.grid_rows):
        for column in range(config.grid_columns):
            for space, stats in (("rgb", ("mean", "std")), ("hsv", ("mean",))):
                for stat in stats:
                    names.extend(
                        f"grid_{row}_{column}_{space}_{channel}_{stat}" for channel in range(3)
                    )
    names.extend(
        [
            "edge_horizontal_mean",
            "edge_horizontal_std",
            "edge_vertical_mean",
            "edge_vertical_std",
            "edge_horizontal_density",
            "edge_vertical_density",
            "saturated_pixel_ratio",
            "dark_pixel_ratio",
            "foreground_proxy_ratio",
        ]
    )
    return names
