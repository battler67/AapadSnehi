from __future__ import annotations

from sklearn.ensemble import (AdaBoostClassifier, AdaBoostRegressor, ExtraTreesClassifier,
                              ExtraTreesRegressor, GradientBoostingClassifier,
                              GradientBoostingRegressor, HistGradientBoostingClassifier,
                              HistGradientBoostingRegressor, RandomForestClassifier,
                              RandomForestRegressor)
from sklearn.dummy import DummyClassifier
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis, QuadraticDiscriminantAnalysis
from sklearn.linear_model import ElasticNet, LogisticRegression, Ridge
from sklearn.naive_bayes import GaussianNB
from sklearn.neighbors import KNeighborsClassifier, KNeighborsRegressor
from sklearn.neural_network import MLPClassifier, MLPRegressor
from sklearn.svm import LinearSVC, LinearSVR, SVC, SVR
from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor


def regression_models(seed: int = 42):
    models = {
        "ridge": (Ridge(alpha=10.0), 196_500),
        "elastic_net": (ElasticNet(alpha=.001, l1_ratio=.2, max_iter=1000, random_state=seed), 150_000),
        "knn": (KNeighborsRegressor(n_neighbors=15, weights="distance", n_jobs=1), 50_000),
        "linear_svr": (LinearSVR(C=.1, epsilon=.05, max_iter=2500, random_state=seed), 100_000),
        "rbf_svr": (SVR(C=10.0, epsilon=.05, gamma="scale", cache_size=2048), 20_000),
        "decision_tree": (DecisionTreeRegressor(max_depth=14, min_samples_leaf=10, random_state=seed), 150_000),
        "random_forest": (RandomForestRegressor(n_estimators=120, max_depth=16, min_samples_leaf=4,
                                                 max_features=.7, n_jobs=8, random_state=seed), 150_000),
        "extra_trees": (ExtraTreesRegressor(n_estimators=120, max_depth=18, min_samples_leaf=3,
                                             max_features=.8, n_jobs=8, random_state=seed), 150_000),
        "adaboost": (AdaBoostRegressor(n_estimators=80, learning_rate=.05, random_state=seed), 80_000),
        "gradient_boosting": (GradientBoostingRegressor(n_estimators=120, max_depth=3, learning_rate=.05,
                                                         loss="huber", random_state=seed), 80_000),
        "hist_gradient_boosting": (HistGradientBoostingRegressor(max_iter=150, max_leaf_nodes=31,
                                                                  learning_rate=.07, early_stopping=False, random_state=seed), 196_500),
        "small_mlp": (MLPRegressor(hidden_layer_sizes=(64, 32), early_stopping=False,
                                    max_iter=100, random_state=seed), 100_000),
    }
    optional = [
        ("xgboost", "xgboost", "XGBRegressor", dict(n_estimators=180, max_depth=6, learning_rate=.05,
          subsample=.8, colsample_bytree=.8, objective="reg:squarederror", n_jobs=8, random_state=seed), 150_000),
        ("lightgbm", "lightgbm", "LGBMRegressor", dict(n_estimators=180, num_leaves=31, learning_rate=.05,
          subsample=.8, colsample_bytree=.8, n_jobs=8, random_state=seed, verbosity=-1), 150_000),
        ("catboost", "catboost", "CatBoostRegressor", dict(iterations=180, depth=7, learning_rate=.05,
          loss_function="RMSE", verbose=False, allow_writing_files=False, thread_count=8, random_seed=seed), 150_000),
    ]
    return models, optional


def classification_models(seed: int = 42):
    models = {
        "dummy_prior": (DummyClassifier(strategy="prior", random_state=seed), 196_500),
        "logistic_regression": (LogisticRegression(C=1.0, max_iter=500, class_weight="balanced", n_jobs=8,
                                                     random_state=seed), 196_500),
        "gaussian_nb": (GaussianNB(), 196_500),
        "lda": (LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto"), 150_000),
        "regularized_qda": (QuadraticDiscriminantAnalysis(reg_param=.2), 80_000),
        "knn": (KNeighborsClassifier(n_neighbors=25, weights="distance", n_jobs=1), 50_000),
        "linear_svm": (LinearSVC(C=.1, class_weight="balanced", max_iter=2500, random_state=seed), 100_000),
        "rbf_svm": (SVC(C=3.0, gamma="scale", class_weight="balanced", probability=False,
                         cache_size=2048, random_state=seed), 20_000),
        "decision_tree": (DecisionTreeClassifier(max_depth=12, min_samples_leaf=10, class_weight="balanced",
                                                  random_state=seed), 150_000),
        "random_forest": (RandomForestClassifier(n_estimators=120, max_depth=16, min_samples_leaf=4,
                                                  max_features=.7, class_weight="balanced_subsample",
                                                  n_jobs=8, random_state=seed), 150_000),
        "extra_trees": (ExtraTreesClassifier(n_estimators=120, max_depth=18, min_samples_leaf=3,
                                              max_features=.8, class_weight="balanced", n_jobs=8,
                                              random_state=seed), 150_000),
        "adaboost": (AdaBoostClassifier(n_estimators=100, learning_rate=.05, random_state=seed), 100_000),
        "gradient_boosting": (GradientBoostingClassifier(n_estimators=120, max_depth=3, learning_rate=.05,
                                                          random_state=seed), 80_000),
        "hist_gradient_boosting": (HistGradientBoostingClassifier(max_iter=150, max_leaf_nodes=31,
                                                                   learning_rate=.07, class_weight="balanced", early_stopping=False,
                                                                   random_state=seed), 196_500),
        "small_mlp": (MLPClassifier(hidden_layer_sizes=(64, 32), early_stopping=False, max_iter=100,
                                     random_state=seed), 100_000),
    }
    optional = [
        ("xgboost", "xgboost", "XGBClassifier", dict(n_estimators=180, max_depth=6, learning_rate=.05,
          subsample=.8, colsample_bytree=.8, eval_metric="logloss", n_jobs=8, random_state=seed), 150_000),
        ("lightgbm", "lightgbm", "LGBMClassifier", dict(n_estimators=180, num_leaves=31, learning_rate=.05,
          subsample=.8, colsample_bytree=.8, class_weight="balanced", n_jobs=8, random_state=seed, verbosity=-1), 150_000),
        ("catboost", "catboost", "CatBoostClassifier", dict(iterations=180, depth=7, learning_rate=.05,
          loss_function="Logloss", auto_class_weights="Balanced", verbose=False, allow_writing_files=False, thread_count=8,
          random_seed=seed), 150_000),
    ]
    return models, optional


def load_optional(specs):
    import importlib
    loaded, failures = {}, {}
    for name, module, class_name, kwargs, cap in specs:
        try:
            loaded[name] = (getattr(importlib.import_module(module), class_name)(**kwargs), cap)
        except Exception as exc:
            failures[name] = f"{type(exc).__name__}: {exc}"
    return loaded, failures
