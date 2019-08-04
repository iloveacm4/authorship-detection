import time
from typing import Tuple, List

import numpy as np
import torch
from sklearn.metrics import accuracy_score
from torch import optim, nn
from torch.utils.data import DataLoader

from classifier.BaseClassifier import BaseClassifier
from classifier.config import Config
from model.ProjectClassifier import ProjectClassifier


class NNClassifier(BaseClassifier):
    def __init__(self, config: Config):
        super(NNClassifier, self).__init__(config)

    def __sample_loaders(self, fold_ind: int = 0) -> Tuple[DataLoader, DataLoader]:
        train_dataset, test_dataset = self._split_train_test(self._loader, fold_ind, pad=True)
        train_loader = DataLoader(train_dataset, self.config.batch_size(), shuffle=True)
        test_loader = DataLoader(test_dataset, self.config.batch_size())
        return train_loader, test_loader

    def __train(self, train_loader, test_loader, model, optimizer, loss_function, n_epochs, log_batches, batch_size):
        print("Start training")
        accuracies = []
        for epoch in range(n_epochs):
            print("Epoch #{}".format(epoch + 1))
            current_loss = 0
            start_time = time.time()
            for n_batch, sample in enumerate(train_loader):
                starts, paths, ends, labels = sample['starts'], sample['paths'], sample['ends'], sample['labels']
                optimizer.zero_grad()

                predictions = model((starts, paths, ends))
                loss = loss_function(predictions, labels)
                loss.backward()
                optimizer.step()

                current_loss += loss.item()
                if (n_batch + 1) % log_batches == 0:
                    print("After {} batches: average loss {}".format(n_batch + 1, current_loss / log_batches))
                    print(f"Throughput {int(log_batches * batch_size / (time.time() - start_time))} examples / sec")
                    current_loss = 0
                    start_time = time.time()

            with torch.no_grad():
                total = len(test_loader.dataset)
                predictions = np.zeros(total)
                targets = np.zeros(total)
                cur = 0
                for sample in test_loader:
                    starts, paths, ends, labels = sample['starts'], sample['paths'], sample['ends'], sample['labels']
                    batched_predictions = model((starts, paths, ends))
                    batched_predictions = np.argmax(batched_predictions, axis=1)
                    batched_targets = labels
                    predictions[cur:cur + len(batched_predictions)] = batched_predictions
                    targets[cur:cur + len(batched_targets)] = batched_targets
                    cur += len(batched_predictions)

                # print(predictions)
                # print(targets)
                accuracy = accuracy_score(targets, predictions)
                print(f"accuracy: {accuracy}")
                accuracies.append(accuracy)

        print("Training completed")
        return accuracies

    def __run_classifier(self, train_loader, test_loader) -> float:
        model = ProjectClassifier(self._loader.tokens().size,
                                  self._loader.paths().size,
                                  dim=self.config.hidden_dim(),
                                  n_classes=self._loader.n_classes())

        optimizer = optim.Adam(model.parameters(), lr=self.config.learning_rate())
        loss_function = nn.CrossEntropyLoss()
        accuracies = self.__train(train_loader, test_loader, model, optimizer, loss_function,
                                  n_epochs=self.config.epochs(),
                                  log_batches=self.config.log_batches(),
                                  batch_size=self.config.batch_size())
        return max(accuracies)

    def cross_validate(self) -> Tuple[float, float, List[float]]:
        print("Begin cross validation")
        scores = []
        for n_fold in range(self._n_folds()):
            train_loader, test_loader = self.__sample_loaders(n_fold)
            scores.append(float(self.__run_classifier(train_loader, test_loader)))
        print(scores)
        return float(np.mean(scores)), float(np.std(scores)), scores
