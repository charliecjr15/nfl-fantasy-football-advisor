"""Train and compare leakage-safe fantasy-point models on validation data."""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from pandas.api.types import is_numeric_dtype
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import (
    HistGradientBoostingRegressor,
    RandomForestRegressor,
)
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from evaluate_baselines import (
    atomic_write_csv,
    load_configuration,
    print_section,
    regression_metrics,
    resolve_project_path,
    round_metric_columns,
    spearman_rank_correlation,
    top_n_overlap_pct,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "model_settings.toml"

SUPPORTED_CANDIDATES = {
    "ridge",
    "random_forest",
    "hist_gradient_boosting",
}

MODEL_TYPES = {
    "rolling_5_game": "selected_baseline",
    "ridge": "trained_candidate",
    "random_forest": "trained_candidate",
    "hist_gradient_boosting": "trained_candidate",
    "position_champion": "selected_position_composite",
}


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description=(
            "Train position-specific fantasy-point models using only "
            "the configured training split and evaluate them on validation."
        )
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG),
        help="Path to the model settings TOML file.",
    )
    return parser.parse_args()


def validate_training_configuration(
    configuration: dict[str, Any],
) -> None:
    """Validate the model-training and test-isolation contract."""

    training = configuration["training"]
    split = configuration["split"]
    model = configuration["model"]
    preprocessing = configuration["preprocessing"]
    baseline = configuration["baseline"]

    evaluation_split = training["evaluation_split"]
    validation_label = split["validation_label"]
    test_label = split["test_label"]

    if evaluation_split != validation_label:
        raise ValueError(
            "Candidate development must use the validation split."
        )

    if evaluation_split == test_label:
        raise ValueError(
            "The test split cannot be used during candidate development."
        )

    if training["allow_test_evaluation"]:
        raise ValueError(
            "allow_test_evaluation must remain false during "
            "candidate development."
        )

    configured_candidates = list(training["candidate_models"])

    if len(configured_candidates) != len(set(configured_candidates)):
        raise ValueError("Candidate model names must be unique.")

    unsupported_candidates = sorted(
        set(configured_candidates) - SUPPORTED_CANDIDATES
    )
    missing_candidates = sorted(
        SUPPORTED_CANDIDATES - set(configured_candidates)
    )

    if unsupported_candidates:
        raise ValueError(
            "Unsupported candidate models: "
            + ", ".join(unsupported_candidates)
        )

    if missing_candidates:
        raise ValueError(
            "Required candidate models are missing: "
            + ", ".join(missing_candidates)
        )

    if not model["train_separate_position_models"]:
        raise ValueError(
            "Version 1 requires separate position models."
        )

    if not training["train_separate_position_models"]:
        raise ValueError(
            "Training must remain position-specific."
        )

    if training["selection_scope"] != "position":
        raise ValueError(
            "Candidate selection must operate by position."
        )

    if training["composite_model_name"] != "position_champion":
        raise ValueError(
            "The configured composite model must be "
            "position_champion."
        )

    if preprocessing["numeric_missing_strategy"] != "median":
        raise ValueError(
            "Version 1 requires median numeric imputation."
        )

    if (
        preprocessing["categorical_missing_strategy"]
        != "most_frequent"
    ):
        raise ValueError(
            "Version 1 requires most-frequent categorical imputation."
        )

    if preprocessing["categorical_encoding"] != "one_hot":
        raise ValueError(
            "Version 1 requires one-hot categorical encoding."
        )

    if not split["fit_preprocessing_on_training_only"]:
        raise ValueError(
            "Preprocessing must be fit on training data only."
        )

    if split["allow_random_split"]:
        raise ValueError(
            "Random model-data splits are not permitted."
        )

    if training["selection_metric"] != "mae":
        raise ValueError("The primary selection metric must be MAE.")

    if training["selection_tiebreaker"] != "rmse":
        raise ValueError("The selection tiebreaker must be RMSE.")

    nonnegative_settings = [
        "minimum_mae_improvement_vs_baseline",
        "maximum_spearman_drop_vs_baseline",
        "maximum_top_n_overlap_drop_pct_vs_baseline",
    ]

    for setting in nonnegative_settings:
        if float(training[setting]) < 0:
            raise ValueError(
                f"{setting} must be zero or greater."
            )

    if baseline["primary_baseline"] != "rolling_5_game":
        raise ValueError(
            "The trained candidates must be compared with "
            "the selected rolling-five-game baseline."
        )

    ridge = training["ridge"]
    random_forest = training["random_forest"]
    boosting = training["hist_gradient_boosting"]

    if float(ridge["alpha"]) <= 0:
        raise ValueError("Ridge alpha must be positive.")

    if int(random_forest["n_estimators"]) <= 0:
        raise ValueError(
            "Random-forest n_estimators must be positive."
        )

    if int(random_forest["min_samples_leaf"]) <= 0:
        raise ValueError(
            "Random-forest min_samples_leaf must be positive."
        )

    if not 0 < float(random_forest["max_features"]) <= 1:
        raise ValueError(
            "Random-forest max_features must be in (0, 1]."
        )

    if int(boosting["max_iter"]) <= 0:
        raise ValueError(
            "Boosting max_iter must be positive."
        )

    if float(boosting["learning_rate"]) <= 0:
        raise ValueError(
            "Boosting learning_rate must be positive."
        )

    if int(boosting["max_leaf_nodes"]) < 2:
        raise ValueError(
            "Boosting max_leaf_nodes must be at least two."
        )

    if int(boosting["min_samples_leaf"]) <= 0:
        raise ValueError(
            "Boosting min_samples_leaf must be positive."
        )

    if boosting["early_stopping"]:
        raise ValueError(
            "Early stopping is disabled so sklearn does not create "
            "a random internal validation split."
        )

    required_outputs = {
        "predictions_path",
        "metrics_path",
        "weekly_metrics_path",
        "comparison_path",
        "position_selection_path",
    }

    configured_outputs = set(training["output"])

    if configured_outputs != required_outputs:
        raise ValueError(
            "Training output configuration must contain exactly: "
            + ", ".join(sorted(required_outputs))
        )


def configured_columns(
    configuration: dict[str, Any],
) -> tuple[list[str], list[str], list[str], str]:
    """Return the model input and target column contract."""

    columns = configuration["columns"]

    categorical_features = list(columns["categorical_features"])
    numeric_features = list(columns["numeric_features"])
    predictor_features = categorical_features + numeric_features
    target = columns["target"]

    if len(predictor_features) != len(set(predictor_features)):
        raise ValueError(
            "Configured predictor feature names must be unique."
        )

    forbidden_overlap = sorted(
        set(predictor_features)
        & set(columns["forbidden_predictors"])
    )

    if forbidden_overlap:
        raise ValueError(
            "Forbidden predictors are configured as features: "
            + ", ".join(forbidden_overlap)
        )

    return (
        categorical_features,
        numeric_features,
        predictor_features,
        target,
    )


def load_development_data(
    parquet_path: Path,
    configuration: dict[str, Any],
) -> pd.DataFrame:
    """Load only training and validation columns and rows."""

    if not parquet_path.exists():
        raise FileNotFoundError(
            "Model Parquet file not found. Run "
            "scripts/export_model_data.py first."
        )

    (
        categorical_features,
        numeric_features,
        _,
        target,
    ) = configured_columns(configuration)

    metadata = list(configuration["columns"]["metadata"])
    required_output_columns = [
        "season",
        "week",
        "game_id",
        "game_date",
        "player_id",
        "player_display_name",
        "position",
        "team",
        "opponent",
        "data_split",
    ]

    selected_columns = list(
        dict.fromkeys(
            metadata
            + required_output_columns
            + categorical_features
            + numeric_features
            + [target]
        )
    )

    split = configuration["split"]
    allowed_splits = [
        split["training_label"],
        split["validation_label"],
    ]

    dataframe = pd.read_parquet(
        parquet_path,
        engine="pyarrow",
        columns=selected_columns,
        filters=[("data_split", "in", allowed_splits)],
    )

    observed_splits = set(
        dataframe["data_split"].dropna().unique()
    )

    unexpected_splits = sorted(
        observed_splits - set(allowed_splits)
    )

    if unexpected_splits:
        raise ValueError(
            "Unexpected data splits loaded: "
            + ", ".join(unexpected_splits)
        )

    if split["test_label"] in observed_splits:
        raise ValueError(
            "Test rows were loaded during model development."
        )

    return dataframe


def unavailable_key_rows(
    dataframe: pd.DataFrame,
    key_columns: list[str],
) -> int:
    """Count rows with null or blank required keys."""

    unavailable = dataframe[key_columns].isna().any(axis=1)

    for column in key_columns:
        if (
            dataframe[column].dtype == object
            or isinstance(dataframe[column].dtype, pd.StringDtype)
        ):
            unavailable = unavailable | (
                dataframe[column]
                .astype("string")
                .str.strip()
                .eq("")
                .fillna(False)
            )

    return int(unavailable.sum())


def validate_development_data(
    dataframe: pd.DataFrame,
    configuration: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Validate training and validation partitions."""

    split = configuration["split"]
    quality = configuration["quality"]
    key = list(configuration["columns"]["key"])

    (
        categorical_features,
        numeric_features,
        predictor_features,
        target,
    ) = configured_columns(configuration)

    training = dataframe.loc[
        dataframe["data_split"].eq(split["training_label"])
    ].copy()

    validation = dataframe.loc[
        dataframe["data_split"].eq(split["validation_label"])
    ].copy()

    duplicate_training_keys = int(
        training.duplicated(key).sum()
    )
    duplicate_validation_keys = int(
        validation.duplicated(key).sum()
    )
    unavailable_training_keys = unavailable_key_rows(
        training,
        key,
    )
    unavailable_validation_keys = unavailable_key_rows(
        validation,
        key,
    )
    missing_training_targets = int(training[target].isna().sum())
    missing_validation_targets = int(
        validation[target].isna().sum()
    )

    missing_predictors = sorted(
        set(predictor_features) - set(dataframe.columns)
    )

    nonnumeric_features = [
        column
        for column in numeric_features
        if not is_numeric_dtype(dataframe[column])
    ]

    expected_positions = set(configuration["model"]["positions"])
    training_positions = set(training["position"].dropna().unique())
    validation_positions = set(
        validation["position"].dropna().unique()
    )

    print(f"training_rows={len(training):,}")
    print(f"validation_rows={len(validation):,}")
    print("test_rows_loaded=0")
    print(f"duplicate_training_keys={duplicate_training_keys}")
    print(
        "duplicate_validation_keys="
        f"{duplicate_validation_keys}"
    )
    print(
        "unavailable_training_keys="
        f"{unavailable_training_keys}"
    )
    print(
        "unavailable_validation_keys="
        f"{unavailable_validation_keys}"
    )
    print(
        "missing_training_targets="
        f"{missing_training_targets}"
    )
    print(
        "missing_validation_targets="
        f"{missing_validation_targets}"
    )
    print(f"configured_predictors={len(predictor_features)}")
    print(f"categorical_predictors={len(categorical_features)}")
    print(f"numeric_predictors={len(numeric_features)}")
    print(f"missing_predictors={missing_predictors}")
    print(f"nonnumeric_features={nonnumeric_features}")

    if len(training) != int(quality["expected_training_rows"]):
        raise ValueError(
            "Training row count does not match configuration."
        )

    if len(validation) != int(
        quality["expected_validation_rows"]
    ):
        raise ValueError(
            "Validation row count does not match configuration."
        )

    if duplicate_training_keys or duplicate_validation_keys:
        raise ValueError(
            "Duplicate model keys were found."
        )

    if unavailable_training_keys or unavailable_validation_keys:
        raise ValueError(
            "Unavailable model keys were found."
        )

    if missing_training_targets or missing_validation_targets:
        raise ValueError(
            "Missing model targets were found."
        )

    if missing_predictors:
        raise ValueError(
            "Configured predictors are missing from the dataset."
        )

    if nonnumeric_features:
        raise ValueError(
            "Configured numeric predictors contain nonnumeric dtypes."
        )

    if training_positions != expected_positions:
        raise ValueError(
            "Training positions do not match configuration."
        )

    if validation_positions != expected_positions:
        raise ValueError(
            "Validation positions do not match configuration."
        )

    return training, validation

## SECTION 2 ##

def prepare_predictors(
    dataframe: pd.DataFrame,
    categorical_features: list[str],
    numeric_features: list[str],
) -> pd.DataFrame:
    """Prepare predictor dtypes without fitting transformations."""

    predictors = dataframe[
        categorical_features + numeric_features
    ].copy()

    for column in categorical_features:
        predictors[column] = (
            predictors[column]
            .astype("object")
            .where(predictors[column].notna(), np.nan)
        )

    for column in numeric_features:
        predictors[column] = pd.to_numeric(
            predictors[column],
            errors="raise",
        )

    return predictors


def build_preprocessor(
    configuration: dict[str, Any],
    *,
    scale_numeric: bool,
) -> ColumnTransformer:
    """Build a training-only preprocessing pipeline."""

    preprocessing = configuration["preprocessing"]

    numeric_steps: list[tuple[str, Any]] = [
        (
            "imputer",
            SimpleImputer(
                strategy=preprocessing[
                    "numeric_missing_strategy"
                ],
                add_indicator=bool(
                    preprocessing["preserve_missingness_flags"]
                ),
                keep_empty_features=True,
            ),
        )
    ]

    if scale_numeric:
        numeric_steps.append(
            ("scaler", StandardScaler())
        )

    numeric_pipeline = Pipeline(numeric_steps)

    categorical_pipeline = Pipeline(
        [
            (
                "imputer",
                SimpleImputer(
                    strategy=preprocessing[
                        "categorical_missing_strategy"
                    ],
                    keep_empty_features=True,
                ),
            ),
            (
                "one_hot",
                OneHotEncoder(
                    handle_unknown="ignore",
                    sparse_output=False,
                    dtype=np.float32,
                ),
            ),
        ]
    )

    return ColumnTransformer(
        transformers=[
            (
                "numeric",
                numeric_pipeline,
                list(
                    configuration["columns"]["numeric_features"]
                ),
            ),
            (
                "categorical",
                categorical_pipeline,
                list(
                    configuration["columns"][
                        "categorical_features"
                    ]
                ),
            ),
        ],
        remainder="drop",
        sparse_threshold=0.0,
        verbose_feature_names_out=False,
    )


def build_candidate_pipeline(
    candidate_name: str,
    configuration: dict[str, Any],
) -> Pipeline:
    """Build one configured candidate model pipeline."""

    training = configuration["training"]
    random_seed = int(configuration["model"]["random_seed"])

    if candidate_name == "ridge":
        settings = training["ridge"]

        estimator = Ridge(
            alpha=float(settings["alpha"]),
            fit_intercept=bool(settings["fit_intercept"]),
        )
        scale_numeric = bool(
            configuration["preprocessing"][
                "scale_numeric_for_linear_models"
            ]
        )

    elif candidate_name == "random_forest":
        settings = training["random_forest"]

        estimator = RandomForestRegressor(
            n_estimators=int(settings["n_estimators"]),
            min_samples_leaf=int(
                settings["min_samples_leaf"]
            ),
            max_features=float(settings["max_features"]),
            n_jobs=int(settings["n_jobs"]),
            random_state=random_seed,
        )
        scale_numeric = False

    elif candidate_name == "hist_gradient_boosting":
        settings = training["hist_gradient_boosting"]

        estimator = HistGradientBoostingRegressor(
            learning_rate=float(settings["learning_rate"]),
            max_iter=int(settings["max_iter"]),
            max_leaf_nodes=int(settings["max_leaf_nodes"]),
            min_samples_leaf=int(
                settings["min_samples_leaf"]
            ),
            l2_regularization=float(
                settings["l2_regularization"]
            ),
            early_stopping=bool(settings["early_stopping"]),
            random_state=random_seed,
        )
        scale_numeric = False

    else:
        raise ValueError(
            f"Unsupported candidate model: {candidate_name}"
        )

    return Pipeline(
        [
            (
                "preprocessor",
                build_preprocessor(
                    configuration,
                    scale_numeric=scale_numeric,
                ),
            ),
            ("model", estimator),
        ]
    )


def load_selected_baseline_predictions(
    configuration: dict[str, Any],
) -> pd.DataFrame:
    """Load and validate the selected baseline predictions."""

    baseline_path = resolve_project_path(
        configuration["baseline"]["output"][
            "predictions_path"
        ]
    )

    if not baseline_path.exists():
        raise FileNotFoundError(
            "Baseline predictions were not found. Run "
            "scripts/evaluate_baselines.py first."
        )

    baseline = pd.read_csv(baseline_path)

    key = list(configuration["columns"]["key"])
    target = configuration["columns"]["target"]
    baseline_name = configuration["baseline"][
        "primary_baseline"
    ]
    prediction_column = f"prediction_{baseline_name}"
    required_columns = (
        key
        + [
            "data_split",
            target,
            prediction_column,
        ]
    )

    missing_columns = sorted(
        set(required_columns) - set(baseline.columns)
    )

    if missing_columns:
        raise ValueError(
            "Baseline prediction file is missing columns: "
            + ", ".join(missing_columns)
        )

    expected_rows = int(
        configuration["quality"]["expected_validation_rows"]
    )
    duplicate_keys = int(baseline.duplicated(key).sum())
    missing_predictions = int(
        baseline[prediction_column].isna().sum()
    )
    observed_splits = set(
        baseline["data_split"].dropna().unique()
    )
    expected_split = {
        configuration["split"]["validation_label"]
    }

    print(f"baseline_rows={len(baseline):,}")
    print(f"baseline_duplicate_keys={duplicate_keys}")
    print(
        "baseline_missing_predictions="
        f"{missing_predictions}"
    )
    print(f"baseline_splits={sorted(observed_splits)}")

    if len(baseline) != expected_rows:
        raise ValueError(
            "Baseline prediction row count is incorrect."
        )

    if duplicate_keys:
        raise ValueError(
            "Baseline predictions contain duplicate keys."
        )

    if missing_predictions:
        raise ValueError(
            "Baseline predictions contain missing values."
        )

    if observed_splits != expected_split:
        raise ValueError(
            "Baseline predictions are not validation-only."
        )

    return baseline[required_columns].copy()


def attach_selected_baseline(
    predictions: pd.DataFrame,
    baseline: pd.DataFrame,
    configuration: dict[str, Any],
) -> pd.DataFrame:
    """Attach baseline predictions with a one-to-one reconciliation."""

    key = list(configuration["columns"]["key"])
    target = configuration["columns"]["target"]
    baseline_name = configuration["baseline"][
        "primary_baseline"
    ]
    prediction_column = f"prediction_{baseline_name}"
    baseline_target = "_baseline_target"

    baseline_for_merge = baseline[
        key + [target, prediction_column]
    ].rename(columns={target: baseline_target})

    merged = predictions.merge(
        baseline_for_merge,
        on=key,
        how="left",
        validate="one_to_one",
    )

    unmatched_rows = int(
        merged[prediction_column].isna().sum()
    )

    target_difference = (
        merged[target] - merged[baseline_target]
    ).abs()

    target_mismatch_rows = int(
        target_difference.gt(1e-9).sum()
        + target_difference.isna().sum()
    )

    print(f"baseline_unmatched_rows={unmatched_rows}")
    print(
        "baseline_target_mismatch_rows="
        f"{target_mismatch_rows}"
    )

    if unmatched_rows:
        raise ValueError(
            "Validation rows are missing baseline predictions."
        )

    if target_mismatch_rows:
        raise ValueError(
            "Baseline targets do not reconcile with model data."
        )

    return merged.drop(columns=[baseline_target])


def train_candidate_predictions(
    training: pd.DataFrame,
    validation: pd.DataFrame,
    baseline: pd.DataFrame,
    configuration: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, float]]:
    """Fit separate position models and create validation predictions."""

    (
        categorical_features,
        numeric_features,
        _,
        target,
    ) = configured_columns(configuration)

    output_columns = [
        "season",
        "week",
        "game_id",
        "game_date",
        "player_id",
        "player_display_name",
        "position",
        "team",
        "opponent",
        "data_split",
        target,
    ]

    predictions = validation[output_columns].copy()
    fit_seconds: dict[str, float] = {}

    positions = list(configuration["model"]["positions"])
    candidates = list(
        configuration["training"]["candidate_models"]
    )

    for candidate_name in candidates:
        prediction_column = f"prediction_{candidate_name}"
        candidate_predictions = pd.Series(
            index=validation.index,
            dtype="float64",
        )
        candidate_start = time.perf_counter()

        for position in positions:
            position_training = training.loc[
                training["position"].eq(position)
            ]
            position_validation = validation.loc[
                validation["position"].eq(position)
            ]

            if position_training.empty:
                raise ValueError(
                    f"No training rows are available for {position}."
                )

            if position_validation.empty:
                raise ValueError(
                    f"No validation rows are available for {position}."
                )

            pipeline = build_candidate_pipeline(
                candidate_name,
                configuration,
            )

            training_predictors = prepare_predictors(
                position_training,
                categorical_features,
                numeric_features,
            )
            validation_predictors = prepare_predictors(
                position_validation,
                categorical_features,
                numeric_features,
            )

            position_start = time.perf_counter()

            pipeline.fit(
                training_predictors,
                position_training[target],
            )

            position_predictions = pipeline.predict(
                validation_predictors
            )

            position_elapsed = (
                time.perf_counter() - position_start
            )

            candidate_predictions.loc[
                position_validation.index
            ] = position_predictions

            print(
                f"{candidate_name} {position}: "
                f"training_rows={len(position_training):,}, "
                f"validation_rows={len(position_validation):,}, "
                f"fit_predict_seconds={position_elapsed:.1f}"
            )

        fit_seconds[candidate_name] = (
            time.perf_counter() - candidate_start
        )

        predictions[prediction_column] = (
            candidate_predictions.reindex(predictions.index)
        )

        print(
            f"{candidate_name}_total_seconds="
            f"{fit_seconds[candidate_name]:.1f}"
        )

    predictions = attach_selected_baseline(
        predictions,
        baseline,
        configuration,
    )

    return predictions.sort_values(
        ["season", "week", "position", "player_id"],
        kind="stable",
    ).reset_index(drop=True), fit_seconds


def validate_prediction_output(
    predictions: pd.DataFrame,
    configuration: dict[str, Any],
) -> None:
    """Validate prediction completeness and test isolation."""

    key = list(configuration["columns"]["key"])
    target = configuration["columns"]["target"]
    baseline_name = configuration["baseline"][
        "primary_baseline"
    ]
    candidates = list(
        configuration["training"]["candidate_models"]
    )
    evaluated_models = [baseline_name] + candidates

    prediction_columns = [
        f"prediction_{model_name}"
        for model_name in evaluated_models
    ]

    expected_rows = int(
        configuration["quality"]["expected_validation_rows"]
    )
    duplicate_keys = int(predictions.duplicated(key).sum())
    unavailable_keys = unavailable_key_rows(
        predictions,
        key,
    )
    missing_targets = int(predictions[target].isna().sum())
    missing_predictions = {
        column: int(predictions[column].isna().sum())
        for column in prediction_columns
    }
    infinite_prediction_rows = int(
        (~np.isfinite(
            predictions[prediction_columns].to_numpy(
                dtype="float64"
            )
        )).any(axis=1).sum()
    )
    observed_splits = set(
        predictions["data_split"].dropna().unique()
    )
    expected_splits = {
        configuration["split"]["validation_label"]
    }

    print(f"validation_predictions={len(predictions):,}")
    print(f"duplicate_prediction_keys={duplicate_keys}")
    print(f"unavailable_prediction_keys={unavailable_keys}")
    print(f"missing_prediction_targets={missing_targets}")
    print(f"missing_predictions={missing_predictions}")
    print(
        "infinite_prediction_rows="
        f"{infinite_prediction_rows}"
    )
    print(f"prediction_splits={sorted(observed_splits)}")
    print("test_rows_evaluated=0")

    if len(predictions) != expected_rows:
        raise ValueError(
            "Prediction output row count is incorrect."
        )

    if duplicate_keys:
        raise ValueError(
            "Prediction output contains duplicate keys."
        )

    if unavailable_keys:
        raise ValueError(
            "Prediction output contains unavailable keys."
        )

    if missing_targets:
        raise ValueError(
            "Prediction output contains missing targets."
        )

    if any(missing_predictions.values()):
        raise ValueError(
            "Prediction output contains missing predictions."
        )

    if infinite_prediction_rows:
        raise ValueError(
            "Prediction output contains non-finite predictions."
        )

    if observed_splits != expected_splits:
        raise ValueError(
            "Prediction output is not validation-only."
        )

## SECTION 3 ##

def build_position_selection(
    predictions: pd.DataFrame,
    configuration: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, str]]:
    """Select the best eligible algorithm for each position."""

    training = configuration["training"]
    target = configuration["columns"]["target"]
    baseline_name = configuration["baseline"][
        "primary_baseline"
    ]
    candidates = list(training["candidate_models"])
    positions = list(configuration["model"]["positions"])
    cutoffs = configuration["evaluation"]["starter_cutoffs"]

    baseline_column = f"prediction_{baseline_name}"
    rows: list[dict[str, Any]] = []

    for position in positions:
        frame = predictions.loc[
            predictions["position"].eq(position)
        ]

        if frame.empty:
            raise ValueError(
                f"No validation rows exist for {position}."
            )

        baseline_mae, baseline_rmse = regression_metrics(
            frame[target],
            frame[baseline_column],
        )
        baseline_spearman = spearman_rank_correlation(
            frame[target],
            frame[baseline_column],
        )

        baseline_top_n_values = [
            top_n_overlap_pct(
                group=group,
                target=target,
                prediction_column=baseline_column,
                cutoff=int(cutoffs[position]),
            )
            for _, group in frame.groupby(
                ["season", "week"],
                sort=True,
            )
        ]
        baseline_top_n = float(
            pd.Series(baseline_top_n_values).mean()
        )

        for candidate_name in candidates:
            candidate_column = (
                f"prediction_{candidate_name}"
            )

            candidate_mae, candidate_rmse = (
                regression_metrics(
                    frame[target],
                    frame[candidate_column],
                )
            )
            candidate_spearman = (
                spearman_rank_correlation(
                    frame[target],
                    frame[candidate_column],
                )
            )

            candidate_top_n_values = [
                top_n_overlap_pct(
                    group=group,
                    target=target,
                    prediction_column=candidate_column,
                    cutoff=int(cutoffs[position]),
                )
                for _, group in frame.groupby(
                    ["season", "week"],
                    sort=True,
                )
            ]
            candidate_top_n = float(
                pd.Series(candidate_top_n_values).mean()
            )

            mae_improvement = float(
                baseline_mae - candidate_mae
            )
            rmse_improvement = float(
                baseline_rmse - candidate_rmse
            )
            spearman_difference = float(
                candidate_spearman - baseline_spearman
            )
            top_n_difference = float(
                candidate_top_n - baseline_top_n
            )

            if baseline_mae == 0:
                mae_improvement_pct = float("nan")
            else:
                mae_improvement_pct = float(
                    100.0
                    * mae_improvement
                    / baseline_mae
                )

            passes_mae = bool(
                mae_improvement
                >= float(
                    training[
                        "minimum_mae_improvement_vs_baseline"
                    ]
                )
            )
            passes_spearman = bool(
                spearman_difference
                >= -float(
                    training[
                        "maximum_spearman_drop_vs_baseline"
                    ]
                )
            )
            passes_top_n = bool(
                top_n_difference
                >= -float(
                    training[
                        "maximum_top_n_overlap_drop_pct_vs_baseline"
                    ]
                )
            )
            eligible = bool(
                passes_mae
                and passes_spearman
                and passes_top_n
            )

            rows.append(
                {
                    "evaluation_split": training[
                        "evaluation_split"
                    ],
                    "position": position,
                    "candidate_model": candidate_name,
                    "baseline_model": baseline_name,
                    "row_count": len(frame),
                    "candidate_mae": candidate_mae,
                    "baseline_mae": baseline_mae,
                    "mae_improvement": mae_improvement,
                    "mae_improvement_pct": (
                        mae_improvement_pct
                    ),
                    "candidate_rmse": candidate_rmse,
                    "baseline_rmse": baseline_rmse,
                    "rmse_improvement": rmse_improvement,
                    "candidate_spearman": (
                        candidate_spearman
                    ),
                    "baseline_spearman": (
                        baseline_spearman
                    ),
                    "spearman_difference": (
                        spearman_difference
                    ),
                    "candidate_top_n_overlap_pct": (
                        candidate_top_n
                    ),
                    "baseline_top_n_overlap_pct": (
                        baseline_top_n
                    ),
                    "top_n_overlap_difference_pct": (
                        top_n_difference
                    ),
                    "passes_mae_requirement": passes_mae,
                    "passes_spearman_guardrail": (
                        passes_spearman
                    ),
                    "passes_top_n_guardrail": passes_top_n,
                    "eligible_for_selection": eligible,
                }
            )

    selection = pd.DataFrame(rows)
    selected_by_position: dict[str, str] = {}

    for position in positions:
        position_rows = selection.loc[
            selection["position"].eq(position)
            & selection["eligible_for_selection"]
        ]

        if position_rows.empty:
            selected_by_position[position] = baseline_name
        else:
            selected_by_position[position] = str(
                position_rows.sort_values(
                    [
                        "candidate_mae",
                        "candidate_rmse",
                        "candidate_model",
                    ],
                    kind="stable",
                ).iloc[0]["candidate_model"]
            )

    selection["selected_model_for_position"] = (
        selection["position"].map(selected_by_position)
    )
    selection["is_selected_for_position"] = (
        selection["candidate_model"].eq(
            selection["selected_model_for_position"]
        )
    )

    position_order = {
        position: index
        for index, position in enumerate(
            positions,
            start=1,
        )
    }
    candidate_order = {
        candidate: index
        for index, candidate in enumerate(
            candidates,
            start=1,
        )
    }

    selection["_position_order"] = (
        selection["position"].map(position_order)
    )
    selection["_candidate_order"] = (
        selection["candidate_model"].map(candidate_order)
    )

    selection = (
        selection.sort_values(
            ["_position_order", "_candidate_order"],
            kind="stable",
        )
        .drop(
            columns=[
                "_position_order",
                "_candidate_order",
            ]
        )
        .reset_index(drop=True)
    )

    return selection, selected_by_position

def add_position_champion_predictions(
    predictions: pd.DataFrame,
    selected_by_position: dict[str, str],
    configuration: dict[str, Any],
) -> pd.DataFrame:
    """Create one composite prediction from position winners."""

    composite_name = configuration["training"][
        "composite_model_name"
    ]
    prediction_column = f"prediction_{composite_name}"
    source_column = f"{composite_name}_source_model"

    result = predictions.copy()
    result[prediction_column] = np.nan
    result[source_column] = ""

    for position in configuration["model"]["positions"]:
        if position not in selected_by_position:
            raise ValueError(
                f"No selected model exists for {position}."
            )

        selected_model = selected_by_position[position]
        selected_prediction_column = (
            f"prediction_{selected_model}"
        )
        position_mask = result["position"].eq(position)

        if selected_prediction_column not in result.columns:
            raise ValueError(
                f"Prediction column is missing for "
                f"{selected_model}."
            )

        result.loc[
            position_mask,
            prediction_column,
        ] = result.loc[
            position_mask,
            selected_prediction_column,
        ]

        result.loc[
            position_mask,
            source_column,
        ] = selected_model

    missing_predictions = int(
        result[prediction_column].isna().sum()
    )
    missing_sources = int(
        result[source_column].eq("").sum()
    )

    print(
        "position_champion_missing_predictions="
        f"{missing_predictions}"
    )
    print(
        "position_champion_missing_sources="
        f"{missing_sources}"
    )
    print(
        "selected_models_by_position="
        f"{selected_by_position}"
    )

    if missing_predictions or missing_sources:
        raise ValueError(
            "Position-champion predictions are incomplete."
        )

    return result

def evaluated_model_names(
    configuration: dict[str, Any],
) -> list[str]:
    """Return baseline, candidates, and composite evaluation order."""

    return [
        configuration["baseline"]["primary_baseline"],
        *list(configuration["training"]["candidate_models"]),
        configuration["training"]["composite_model_name"],
    ]

def build_model_weekly_metrics(
    predictions: pd.DataFrame,
    configuration: dict[str, Any],
) -> pd.DataFrame:
    """Calculate weekly position-level metrics for every model."""

    target = configuration["columns"]["target"]
    cutoffs = configuration["evaluation"]["starter_cutoffs"]
    model_names = evaluated_model_names(configuration)

    rows: list[dict[str, Any]] = []

    grouped = predictions.groupby(
        ["season", "week", "position"],
        sort=True,
    )

    for model_name in model_names:
        prediction_column = f"prediction_{model_name}"

        for (
            season,
            week,
            position,
        ), group in grouped:
            mae, rmse = regression_metrics(
                group[target],
                group[prediction_column],
            )

            rows.append(
                {
                    "evaluation_split": configuration[
                        "training"
                    ]["evaluation_split"],
                    "model_name": model_name,
                    "model_type": MODEL_TYPES[model_name],
                    "season": int(season),
                    "week": int(week),
                    "position": position,
                    "row_count": len(group),
                    "starter_cutoff": int(cutoffs[position]),
                    "mae": mae,
                    "rmse": rmse,
                    "spearman_rank_correlation": (
                        spearman_rank_correlation(
                            group[target],
                            group[prediction_column],
                        )
                    ),
                    "top_n_overlap_pct": top_n_overlap_pct(
                        group=group,
                        target=target,
                        prediction_column=prediction_column,
                        cutoff=int(cutoffs[position]),
                    ),
                }
            )

    weekly_metrics = pd.DataFrame(rows)

    model_order = {
        model_name: index
        for index, model_name in enumerate(
            model_names,
            start=1,
        )
    }
    position_order = {
        position: index
        for index, position in enumerate(
            configuration["model"]["positions"],
            start=1,
        )
    }

    weekly_metrics["_model_order"] = (
        weekly_metrics["model_name"].map(model_order)
    )
    weekly_metrics["_position_order"] = (
        weekly_metrics["position"].map(position_order)
    )

    return (
        weekly_metrics.sort_values(
            [
                "_model_order",
                "season",
                "week",
                "_position_order",
            ],
            kind="stable",
        )
        .drop(
            columns=[
                "_model_order",
                "_position_order",
            ]
        )
        .reset_index(drop=True)
    )


def build_model_summary_metrics(
    predictions: pd.DataFrame,
    weekly_metrics: pd.DataFrame,
    fit_seconds: dict[str, float],
    configuration: dict[str, Any],
) -> pd.DataFrame:
    """Calculate overall and position metrics for every model."""

    target = configuration["columns"]["target"]
    model_names = evaluated_model_names(configuration)
    positions = list(configuration["model"]["positions"])

    scopes: list[tuple[str, str | None]] = [
        ("overall", None),
        *[("position", position) for position in positions],
    ]

    rows: list[dict[str, Any]] = []

    for model_name in model_names:
        prediction_column = f"prediction_{model_name}"

        for scope, position in scopes:
            if position is None:
                frame = predictions
                weekly = weekly_metrics.loc[
                    weekly_metrics["model_name"].eq(
                        model_name
                    )
                ]
                scope_label = "ALL"
            else:
                frame = predictions.loc[
                    predictions["position"].eq(position)
                ]
                weekly = weekly_metrics.loc[
                    weekly_metrics["model_name"].eq(
                        model_name
                    )
                    & weekly_metrics["position"].eq(position)
                ]
                scope_label = position

            mae, rmse = regression_metrics(
                frame[target],
                frame[prediction_column],
            )

            rows.append(
                {
                    "evaluation_split": configuration[
                        "training"
                    ]["evaluation_split"],
                    "model_name": model_name,
                    "model_type": MODEL_TYPES[model_name],
                    "scope": scope,
                    "position": scope_label,
                    "row_count": len(frame),
                    "fit_seconds": fit_seconds.get(
                        model_name,
                        float("nan"),
                    ),
                    "mae": mae,
                    "rmse": rmse,
                    "spearman_rank_correlation": (
                        spearman_rank_correlation(
                            frame[target],
                            frame[prediction_column],
                        )
                    ),
                    "mean_weekly_spearman": weekly[
                        "spearman_rank_correlation"
                    ].mean(),
                    "mean_top_n_overlap_pct": weekly[
                        "top_n_overlap_pct"
                    ].mean(),
                }
            )

    summary = pd.DataFrame(rows)

    model_order = {
        model_name: index
        for index, model_name in enumerate(
            model_names,
            start=1,
        )
    }
    scope_order = {
        "ALL": 0,
        **{
            position: index
            for index, position in enumerate(
                positions,
                start=1,
            )
        },
    }

    summary["_model_order"] = summary["model_name"].map(
        model_order
    )
    summary["_scope_order"] = summary["position"].map(
        scope_order
    )

    return (
        summary.sort_values(
            ["_model_order", "_scope_order"],
            kind="stable",
        )
        .drop(
            columns=[
                "_model_order",
                "_scope_order",
            ]
        )
        .reset_index(drop=True)
    )


def build_model_comparison(
    summary_metrics: pd.DataFrame,
    configuration: dict[str, Any],
) -> tuple[pd.DataFrame, str]:
    """Compare candidates with the selected baseline and choose a leader."""

    training = configuration["training"]
    baseline_name = configuration["baseline"][
        "primary_baseline"
    ]

    candidates = [
        *list(training["candidate_models"]),
        training["composite_model_name"],
    ]

    overall = (
        summary_metrics.loc[
            summary_metrics["scope"].eq("overall")
        ]
        .set_index("model_name")
    )

    if baseline_name not in overall.index:
        raise ValueError(
            "Selected baseline is missing from summary metrics."
        )

    baseline = overall.loc[baseline_name]
    rows: list[dict[str, Any]] = []

    for candidate_name in candidates:
        if candidate_name not in overall.index:
            raise ValueError(
                f"{candidate_name} is missing from summary metrics."
            )

        candidate = overall.loc[candidate_name]

        mae_improvement = float(
            baseline["mae"] - candidate["mae"]
        )
        rmse_improvement = float(
            baseline["rmse"] - candidate["rmse"]
        )
        spearman_difference = float(
            candidate["spearman_rank_correlation"]
            - baseline["spearman_rank_correlation"]
        )
        top_n_difference = float(
            candidate["mean_top_n_overlap_pct"]
            - baseline["mean_top_n_overlap_pct"]
        )

        if float(baseline["mae"]) == 0:
            mae_improvement_pct = float("nan")
        else:
            mae_improvement_pct = float(
                100.0
                * mae_improvement
                / float(baseline["mae"])
            )

        passes_mae = bool(
            mae_improvement
            >= float(
                training[
                    "minimum_mae_improvement_vs_baseline"
                ]
            )
        )
        passes_spearman = bool(
            spearman_difference
            >= -float(
                training[
                    "maximum_spearman_drop_vs_baseline"
                ]
            )
        )
        passes_top_n = bool(
            top_n_difference
            >= -float(
                training[
                    "maximum_top_n_overlap_drop_pct_vs_baseline"
                ]
            )
        )
        eligible = bool(
            passes_mae
            and passes_spearman
            and passes_top_n
        )

        rows.append(
            {
                "evaluation_split": training[
                    "evaluation_split"
                ],
                "candidate_model": candidate_name,
                "baseline_model": baseline_name,
                "row_count": int(candidate["row_count"]),
                "candidate_mae": float(candidate["mae"]),
                "baseline_mae": float(baseline["mae"]),
                "mae_improvement": mae_improvement,
                "mae_improvement_pct": mae_improvement_pct,
                "candidate_rmse": float(candidate["rmse"]),
                "baseline_rmse": float(baseline["rmse"]),
                "rmse_improvement": rmse_improvement,
                "candidate_spearman": float(
                    candidate[
                        "spearman_rank_correlation"
                    ]
                ),
                "baseline_spearman": float(
                    baseline[
                        "spearman_rank_correlation"
                    ]
                ),
                "spearman_difference": spearman_difference,
                "candidate_top_n_overlap_pct": float(
                    candidate["mean_top_n_overlap_pct"]
                ),
                "baseline_top_n_overlap_pct": float(
                    baseline["mean_top_n_overlap_pct"]
                ),
                "top_n_overlap_difference_pct": top_n_difference,
                "passes_mae_requirement": passes_mae,
                "passes_spearman_guardrail": passes_spearman,
                "passes_top_n_guardrail": passes_top_n,
                "eligible_for_selection": eligible,
            }
        )

    comparison = pd.DataFrame(rows)

    eligible_candidates = comparison.loc[
        comparison["eligible_for_selection"]
    ].copy()

    if eligible_candidates.empty:
        selected_model = baseline_name
    else:
        selected_model = str(
            eligible_candidates.sort_values(
                [
                    "candidate_mae",
                    "candidate_rmse",
                    "candidate_model",
                ],
                kind="stable",
            ).iloc[0]["candidate_model"]
        )

    comparison["selected_validation_model"] = selected_model
    comparison["is_selected_model"] = comparison[
        "candidate_model"
    ].eq(selected_model)

    return comparison.sort_values(
        [
            "eligible_for_selection",
            "candidate_mae",
            "candidate_rmse",
            "candidate_model",
        ],
        ascending=[False, True, True, True],
        kind="stable",
    ).reset_index(drop=True), selected_model


def prepare_model_prediction_output(
    predictions: pd.DataFrame,
    configuration: dict[str, Any],
) -> pd.DataFrame:
    """Select the auditable model-prediction output columns."""

    target = configuration["columns"]["target"]
    model_names = evaluated_model_names(configuration)

    output_columns = [
        "season",
        "week",
        "game_id",
        "game_date",
        "player_id",
        "player_display_name",
        "position",
        "team",
        "opponent",
        "data_split",
        target,
        *[
            f"prediction_{model_name}"
            for model_name in model_names
        ],
        (
            f"{configuration['training']['composite_model_name']}"
            "_source_model"
        ),
    ]

    return predictions[output_columns].sort_values(
        ["season", "week", "position", "player_id"],
        kind="stable",
    ).reset_index(drop=True)


def round_comparison_columns(
    comparison: pd.DataFrame,
) -> pd.DataFrame:
    """Round presentation fields in the comparison output."""

    result = comparison.copy()

    columns = [
        "candidate_mae",
        "baseline_mae",
        "mae_improvement",
        "mae_improvement_pct",
        "candidate_rmse",
        "baseline_rmse",
        "rmse_improvement",
        "candidate_spearman",
        "baseline_spearman",
        "spearman_difference",
        "candidate_top_n_overlap_pct",
        "baseline_top_n_overlap_pct",
        "top_n_overlap_difference_pct",
    ]

    for column in columns:
        result[column] = result[column].round(4)

    return result

def validate_position_selection(
    position_selection: pd.DataFrame,
    selected_by_position: dict[str, str],
    configuration: dict[str, Any],
) -> None:
    """Validate the position-level selection table."""

    positions = list(configuration["model"]["positions"])
    candidates = list(
        configuration["training"]["candidate_models"]
    )

    expected_rows = len(positions) * len(candidates)
    duplicate_rows = int(
        position_selection.duplicated(
            ["position", "candidate_model"]
        ).sum()
    )
    missing_selected_models = int(
        position_selection[
            "selected_model_for_position"
        ].isna().sum()
    )
    selection_flag_mismatches = int(
        (
            position_selection[
                "is_selected_for_position"
            ]
            != position_selection["candidate_model"].eq(
                position_selection[
                    "selected_model_for_position"
                ]
            )
        ).sum()
    )
    observed_positions = set(
        position_selection["position"].unique()
    )
    inconsistent_selection_groups = int(
        position_selection.groupby("position")[
            "selected_model_for_position"
        ]
        .nunique()
        .ne(1)
        .sum()
    )

    print(
        "position_selection_rows="
        f"{len(position_selection):,}"
    )
    print(
        "expected_position_selection_rows="
        f"{expected_rows:,}"
    )
    print(
        "duplicate_position_selection_rows="
        f"{duplicate_rows}"
    )
    print(
        "missing_position_selected_models="
        f"{missing_selected_models}"
    )
    print(
        "position_selection_flag_mismatches="
        f"{selection_flag_mismatches}"
    )
    print(
        "inconsistent_position_selection_groups="
        f"{inconsistent_selection_groups}"
    )

    if len(position_selection) != expected_rows:
        raise ValueError(
            "Position-selection row count is incorrect."
        )

    if duplicate_rows:
        raise ValueError(
            "Position-selection keys are duplicated."
        )

    if missing_selected_models:
        raise ValueError(
            "Position-selection models are missing."
        )

    if selection_flag_mismatches:
        raise ValueError(
            "Position-selection flags are inconsistent."
        )

    if inconsistent_selection_groups:
        raise ValueError(
            "A position contains multiple selected models."
        )

    if observed_positions != set(positions):
        raise ValueError(
            "Position-selection coverage is incomplete."
        )

    if set(selected_by_position) != set(positions):
        raise ValueError(
            "Selected-model mapping is incomplete."
        )

    for position in positions:
        observed_model = str(
            position_selection.loc[
                position_selection["position"].eq(position),
                "selected_model_for_position",
            ].iloc[0]
        )

        if observed_model != selected_by_position[position]:
            raise ValueError(
                f"Selected model mismatch for {position}."
            )

def validate_metric_outputs(
    predictions: pd.DataFrame,
    summary_metrics: pd.DataFrame,
    weekly_metrics: pd.DataFrame,
    comparison: pd.DataFrame,
    selected_model: str,
    configuration: dict[str, Any],
) -> None:
    """Validate evaluation-table grains and completeness."""

    model_names = evaluated_model_names(configuration)
    positions = list(configuration["model"]["positions"])

    expected_summary_rows = len(model_names) * (
        1 + len(positions)
    )
    position_week_groups = predictions.groupby(
        ["season", "week", "position"]
    ).ngroups
    expected_weekly_rows = (
        len(model_names) * position_week_groups
    )
    expected_comparison_rows = (
        len(configuration["training"]["candidate_models"])
        + 1
    )

    duplicate_summary_rows = int(
        summary_metrics.duplicated(
            ["model_name", "scope", "position"]
        ).sum()
    )
    duplicate_weekly_rows = int(
        weekly_metrics.duplicated(
            ["model_name", "season", "week", "position"]
        ).sum()
    )
    duplicate_comparison_rows = int(
        comparison.duplicated(["candidate_model"]).sum()
    )

    print(f"summary_metric_rows={len(summary_metrics):,}")
    print(f"expected_summary_rows={expected_summary_rows:,}")
    print(f"weekly_metric_rows={len(weekly_metrics):,}")
    print(f"expected_weekly_rows={expected_weekly_rows:,}")
    print(f"comparison_rows={len(comparison):,}")
    print(
        "expected_comparison_rows="
        f"{expected_comparison_rows:,}"
    )
    print(
        "duplicate_summary_rows="
        f"{duplicate_summary_rows}"
    )
    print(
        "duplicate_weekly_rows="
        f"{duplicate_weekly_rows}"
    )
    print(
        "duplicate_comparison_rows="
        f"{duplicate_comparison_rows}"
    )
    print(f"selected_validation_model={selected_model}")

    if len(summary_metrics) != expected_summary_rows:
        raise ValueError(
            "Summary metric row count is incorrect."
        )

    if len(weekly_metrics) != expected_weekly_rows:
        raise ValueError(
            "Weekly metric row count is incorrect."
        )

    if len(comparison) != expected_comparison_rows:
        raise ValueError(
            "Comparison row count is incorrect."
        )

    if (
        duplicate_summary_rows
        or duplicate_weekly_rows
        or duplicate_comparison_rows
    ):
        raise ValueError(
            "Duplicate metric-output keys were found."
        )

    if selected_model not in model_names:
        raise ValueError(
            "Selected validation model is not recognized."
        )


def validate_written_outputs(
    prediction_path: Path,
    metrics_path: Path,
    weekly_path: Path,
    comparison_path: Path,
    position_selection_path: Path,
    configuration: dict[str, Any],
) -> None:
    """Reopen written CSV files and validate their contracts."""

    predictions = pd.read_csv(prediction_path)
    metrics = pd.read_csv(metrics_path)
    weekly = pd.read_csv(weekly_path)
    comparison = pd.read_csv(comparison_path)
    position_selection = pd.read_csv(
        position_selection_path
    )

    expected_prediction_rows = int(
        configuration["quality"]["expected_validation_rows"]
    )
    expected_models = len(
        evaluated_model_names(configuration)
    )
    expected_metric_rows = expected_models * (
        1 + len(configuration["model"]["positions"])
    )
    expected_weekly_rows = (
        expected_models
        * predictions.groupby(
            ["season", "week", "position"]
        ).ngroups
    )
    expected_comparison_rows = (
        len(configuration["training"]["candidate_models"])
        + 1
    )
    expected_position_selection_rows = (
        len(configuration["model"]["positions"])
        * len(configuration["training"]["candidate_models"])
    )

    prediction_columns = [
        f"prediction_{model_name}"
        for model_name in evaluated_model_names(
            configuration
        )
    ]

    composite_name = configuration["training"][
        "composite_model_name"
    ]
    source_column = f"{composite_name}_source_model"

    observed_splits = set(
        predictions["data_split"].dropna().unique()
    )
    expected_splits = {
        configuration["split"]["validation_label"]
    }

    written_missing_predictions = int(
        predictions[prediction_columns].isna().sum().sum()
    )
    written_missing_sources = int(
        (
            predictions[source_column].isna()
            | predictions[source_column]
            .astype("string")
            .str.strip()
            .eq("")
            .fillna(True)
        ).sum()
    )

    selected_values = set(
        comparison["selected_validation_model"]
        .dropna()
        .unique()
    )
    selected_position_count = int(
        position_selection[
            [
                "position",
                "selected_model_for_position",
            ]
        ]
        .drop_duplicates()
        .shape[0]
    )
    duplicate_position_selection_rows = int(
        position_selection.duplicated(
            ["position", "candidate_model"]
        ).sum()
    )

    print(
        "written_prediction_rows="
        f"{len(predictions):,}"
    )
    print(f"written_metric_rows={len(metrics):,}")
    print(f"written_weekly_rows={len(weekly):,}")
    print(
        "written_comparison_rows="
        f"{len(comparison):,}"
    )
    print(
        "written_position_selection_rows="
        f"{len(position_selection):,}"
    )
    print(
        "written_missing_predictions="
        f"{written_missing_predictions}"
    )
    print(
        "written_missing_composite_sources="
        f"{written_missing_sources}"
    )
    print(f"written_splits={sorted(observed_splits)}")
    print(
        "written_selected_models="
        f"{sorted(selected_values)}"
    )
    print(
        "written_selected_position_count="
        f"{selected_position_count}"
    )
    print(
        "written_duplicate_position_selection_rows="
        f"{duplicate_position_selection_rows}"
    )

    if len(predictions) != expected_prediction_rows:
        raise ValueError(
            "Written prediction row count is incorrect."
        )

    if len(metrics) != expected_metric_rows:
        raise ValueError(
            "Written metric row count is incorrect."
        )

    if len(weekly) != expected_weekly_rows:
        raise ValueError(
            "Written weekly row count is incorrect."
        )

    if len(comparison) != expected_comparison_rows:
        raise ValueError(
            "Written comparison row count is incorrect."
        )

    if (
        len(position_selection)
        != expected_position_selection_rows
    ):
        raise ValueError(
            "Written position-selection row count is incorrect."
        )

    if written_missing_predictions:
        raise ValueError(
            "Written predictions contain missing values."
        )

    if written_missing_sources:
        raise ValueError(
            "Written composite sources are incomplete."
        )

    if observed_splits != expected_splits:
        raise ValueError(
            "Written predictions are not validation-only."
        )

    if len(selected_values) != 1:
        raise ValueError(
            "Written comparison does not contain one "
            "selected validation model."
        )

    if selected_position_count != len(
        configuration["model"]["positions"]
    ):
        raise ValueError(
            "Written position selections are incomplete."
        )

    if duplicate_position_selection_rows:
        raise ValueError(
            "Written position selections contain duplicate keys."
        )


def main() -> None:
    """Run training-only fitting and validation-only comparison."""

    arguments = parse_arguments()
    configuration_path = Path(arguments.config).resolve()
    configuration = load_configuration(configuration_path)

    validate_training_configuration(configuration)

    parquet_path = resolve_project_path(
        configuration["export"]["parquet_path"]
    )

    output = configuration["training"]["output"]
    prediction_path = resolve_project_path(
        output["predictions_path"]
    )
    metrics_path = resolve_project_path(
        output["metrics_path"]
    )
    weekly_path = resolve_project_path(
        output["weekly_metrics_path"]
    )
    comparison_path = resolve_project_path(
        output["comparison_path"]
    )
    position_selection_path = resolve_project_path(
        output["position_selection_path"]
    )

    print_section("NFL FANTASY TRAINED MODEL EVALUATION")
    print(f"Configuration: {configuration_path}")
    print(f"Input Parquet: {parquet_path}")
    print(
        "Candidate models: "
        + ", ".join(
            configuration["training"]["candidate_models"]
        )
    )
    print(
        "Evaluation split: "
        f"{configuration['training']['evaluation_split']}"
    )
    print(
        "Test evaluation allowed: "
        f"{configuration['training']['allow_test_evaluation']}"
    )
    print("Position-specific models: True")
    print(
        "Selection scope: "
        f"{configuration['training']['selection_scope']}"
    )
    print(
        "Composite model: "
        f"{configuration['training']['composite_model_name']}"
    )

    print_section("LOADING DEVELOPMENT DATA")

    dataframe = load_development_data(
        parquet_path,
        configuration,
    )

    training, validation = validate_development_data(
        dataframe,
        configuration,
    )

    print_section("LOADING SELECTED BASELINE")

    baseline = load_selected_baseline_predictions(
        configuration
    )

    print_section("FITTING TRAINING-ONLY CANDIDATE MODELS")

    predictions, fit_seconds = train_candidate_predictions(
        training,
        validation,
        baseline,
        configuration,
    )

    print_section("VALIDATING CANDIDATE PREDICTIONS")

    validate_prediction_output(
        predictions,
        configuration,
    )

    print_section("SELECTING POSITION-SPECIFIC CHAMPIONS")

    (
        position_selection,
        selected_by_position,
    ) = build_position_selection(
        predictions,
        configuration,
    )

    validate_position_selection(
        position_selection,
        selected_by_position,
        configuration,
    )

    predictions = add_position_champion_predictions(
        predictions,
        selected_by_position,
        configuration,
    )

    selected_position_rows = (
        position_selection.loc[
            position_selection[
                "is_selected_for_position"
            ]
        ][
            [
                "position",
                "candidate_model",
                "candidate_mae",
                "baseline_mae",
                "mae_improvement",
                "candidate_spearman",
                "candidate_top_n_overlap_pct",
            ]
        ]
        .sort_values("position")
        .copy()
    )

    for column in [
        "candidate_mae",
        "baseline_mae",
        "mae_improvement",
        "candidate_spearman",
        "candidate_top_n_overlap_pct",
    ]:
        selected_position_rows[column] = (
            selected_position_rows[column].round(4)
        )

    print()
    print(selected_position_rows.to_string(index=False))

    print_section("CALCULATING VALIDATION METRICS")

    weekly_metrics = build_model_weekly_metrics(
        predictions,
        configuration,
    )

    summary_metrics = build_model_summary_metrics(
        predictions,
        weekly_metrics,
        fit_seconds,
        configuration,
    )

    comparison, selected_model = build_model_comparison(
        summary_metrics,
        configuration,
    )

    validate_metric_outputs(
        predictions,
        summary_metrics,
        weekly_metrics,
        comparison,
        selected_model,
        configuration,
    )

    overall_display = (
        summary_metrics.loc[
            summary_metrics["scope"].eq("overall")
        ][
            [
                "model_name",
                "model_type",
                "row_count",
                "mae",
                "rmse",
                "spearman_rank_correlation",
                "mean_weekly_spearman",
                "mean_top_n_overlap_pct",
                "fit_seconds",
            ]
        ]
        .sort_values(
            ["mae", "rmse"],
            kind="stable",
        )
        .copy()
    )

    for column in [
        "mae",
        "rmse",
        "spearman_rank_correlation",
        "mean_weekly_spearman",
        "mean_top_n_overlap_pct",
        "fit_seconds",
    ]:
        overall_display[column] = (
            overall_display[column].round(4)
        )

    print()
    print(overall_display.to_string(index=False))

    comparison_display = round_comparison_columns(
        comparison
    )

    print()
    print(
        comparison_display[
            [
                "candidate_model",
                "candidate_mae",
                "mae_improvement",
                "candidate_spearman",
                "spearman_difference",
                "candidate_top_n_overlap_pct",
                "top_n_overlap_difference_pct",
                "eligible_for_selection",
                "is_selected_model",
            ]
        ].to_string(index=False)
    )

    print(f"selected_validation_model={selected_model}")
    print("test_rows_evaluated=0")

    print_section("WRITING TRAINED MODEL RESULTS")

    prediction_output = prepare_model_prediction_output(
        predictions,
        configuration,
    )
    metrics_output = round_metric_columns(summary_metrics)
    metrics_output["fit_seconds"] = (
        metrics_output["fit_seconds"].round(1)
    )
    weekly_output = round_metric_columns(weekly_metrics)
    comparison_output = round_comparison_columns(comparison)
    position_selection_output = round_comparison_columns(
        position_selection
    )

    atomic_write_csv(
        prediction_output,
        prediction_path,
    )
    atomic_write_csv(
        metrics_output,
        metrics_path,
    )
    atomic_write_csv(
        weekly_output,
        weekly_path,
    )
    atomic_write_csv(
        comparison_output,
        comparison_path,
    )
    atomic_write_csv(
        position_selection_output,
        position_selection_path,
    )

    print(
        f"Wrote {prediction_path.relative_to(PROJECT_ROOT)}: "
        f"{len(prediction_output):,} rows"
    )
    print(
        f"Wrote {metrics_path.relative_to(PROJECT_ROOT)}: "
        f"{len(metrics_output):,} rows"
    )
    print(
        f"Wrote {weekly_path.relative_to(PROJECT_ROOT)}: "
        f"{len(weekly_output):,} rows"
    )
    print(
        f"Wrote {comparison_path.relative_to(PROJECT_ROOT)}: "
        f"{len(comparison_output):,} rows"
    )
    print(
        f"Wrote "
        f"{position_selection_path.relative_to(PROJECT_ROOT)}: "
        f"{len(position_selection_output):,} rows"
    )

    print_section("REOPENING WRITTEN RESULTS")

    validate_written_outputs(
        prediction_path,
        metrics_path,
        weekly_path,
        comparison_path,
        position_selection_path,
        configuration,
    )

    print_section("TRAINED MODEL EVALUATION COMPLETE")
    print("development_data_quality=PASS")
    print("validation_predictions_complete=PASS")
    print("position_selection_quality=PASS")
    print("metric_output_quality=PASS")
    print("test_split_untouched=PASS")
    print("trained_model_evaluation_status=PASS")


if __name__ == "__main__":
    main()