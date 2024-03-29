# Lint as: python3
# Copyright 2019 The TensorFlow Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
# pylint: disable=redefined-outer-name
# pylint: disable=g-bad-import-order
"""Build and train neural networks."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import argparse
import datetime
import os
from data_load import DataLoader

import numpy as np
import statistics
import tensorflow as tf
from tensorflow.python.ops.nn_impl import log_poisson_loss

logdir = "logs/scalars/" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
tensorboard_callback = tf.keras.callbacks.TensorBoard(log_dir=logdir)

accuracies = []
conf_matrices = []    



def reshape_function(data, label):
  reshaped_data = tf.reshape(data, [-1, 1, 1])
  return reshaped_data, label


def calculate_model_size(model):
  print(model.summary())
  var_sizes = [
      np.product(list(map(int, v.shape))) * v.dtype.size
      for v in model.trainable_variables
  ]
  print("Model size:", sum(var_sizes) / 1024, "KB")


def build_cnn(seq_length):
  """Builds a convolutional neural network in Keras."""
  SEED = 42
  tf.config.experimental.enable_op_determinism()
  tf.random.set_seed(SEED)
  model = tf.keras.Sequential([
      tf.keras.layers.Conv2D(
          8, (4, 1),
          padding="same",
          activation="relu",
          input_shape=(seq_length, 1, 1),kernel_initializer=tf.keras.initializers.GlorotUniform(seed=SEED)),  # output_shape=(batch, 128, 3, 8)
      tf.keras.layers.MaxPool2D((3, 1)),  # (batch, 42, 1, 8)
      tf.keras.layers.Dropout(0.1),  # (batch, 42, 1, 8)
      tf.keras.layers.Conv2D(16, (4, 1), padding="same",
                             activation="relu",kernel_initializer=tf.keras.initializers.GlorotUniform(seed=SEED)),  # (batch, 42, 1, 16)
      tf.keras.layers.MaxPool2D((2, 1), padding="same", name="2ndPooling"),  # (batch, 14, 1, 16)
      tf.keras.layers.AveragePooling2D(pool_size=(2, 1), padding="same"),
      tf.keras.layers.Dropout(0.1),  # (batch, 14, 1, 16)
      tf.keras.layers.Flatten(),  # (batch, 224)
      tf.keras.layers.Dense(16, activation="relu"),  # (batch, 16)
      tf.keras.layers.Dropout(0.1),  # (batch, 16)
      tf.keras.layers.Dense(2, activation="softmax")  # (batch, 4)
  ])
  model_path = os.path.join("./netmodels", "CNN")
  print("Built CNN.")
  if not os.path.exists(model_path):
    os.makedirs(model_path)
  # model.load_weights("./netmodels/CNN/weights.h5", by_name=True)
  return model, model_path


def build_lstm(seq_length):
  """Builds an LSTM in Keras."""
  model = tf.keras.Sequential([
      tf.keras.layers.Bidirectional(
          tf.keras.layers.LSTM(22),
          input_shape=(seq_length, 1)),  # output_shape=(batch, 44)
      tf.keras.layers.Dense(2, activation="sigmoid")  # (batch, 4)
  ])
  model_path = os.path.join("./netmodels", "LSTM")
  print("Built LSTM.")
  if not os.path.exists(model_path):
    os.makedirs(model_path)
  return model, model_path


def load_data(train_data_path, valid_data_path, test_data_path, seq_length):
  data_loader = DataLoader(train_data_path,
                           valid_data_path,
                           test_data_path,
                           seq_length=seq_length)
  data_loader.format()
  return data_loader.train_len, data_loader.train_data, data_loader.valid_len, \
      data_loader.valid_data, data_loader.test_len, data_loader.test_data


def build_net(args, seq_length):
  if args.model == "CNN":
    model, model_path = build_cnn(seq_length)
  elif args.model == "LSTM":
    model, model_path = build_lstm(seq_length)
  else:
    print("Please input correct model name.(CNN  LSTM)")
  return model, model_path


def train_net(
    model,
    model_path,  # pylint: disable=unused-argument
    train_len,  # pylint: disable=unused-argument
    train_data,
    valid_len,
    valid_data,  # pylint: disable=unused-argument
    test_len,
    test_data,
    kind):
  """Trains the model."""
  calculate_model_size(model)
  epochs = 85
  batch_size = 32
  model.compile(tf.keras.optimizers.Adam(learning_rate=5e-4),
                loss="sparse_categorical_crossentropy",
                metrics=["accuracy"])
  if kind == "CNN":
    train_data = train_data.map(reshape_function)
    test_data = test_data.map(reshape_function)
    valid_data = valid_data.map(reshape_function)
  test_labels = np.zeros(test_len)
  idx = 0
  for data, label in test_data:  # pylint: disable=unused-variable
    test_labels[idx] = label.numpy()
    idx += 1
  train_data = train_data.batch(batch_size).repeat()
  valid_data = valid_data.batch(batch_size)
  test_data = test_data.batch(batch_size)
  model.fit(train_data,
            epochs=epochs,
            validation_data=valid_data,
            steps_per_epoch=1000,
            validation_steps=int((valid_len - 1) / batch_size + 1),
            callbacks=[tensorboard_callback])
  loss, acc = model.evaluate(test_data)
  pred = np.argmax(model.predict(test_data), axis=1)
  confusion = tf.math.confusion_matrix(labels=tf.constant(test_labels),
                                       predictions=tf.constant(pred),
                                       num_classes=2)
  print(confusion)
  print("Loss {}, Accuracy {}".format(loss, acc))
  accuracies.append(acc)
  conf_matrices.append(confusion)
  # Convert the model to the TensorFlow Lite format without quantization
  # converter = tf.lite.TFLiteConverter.from_keras_model(model)
  # only needed for LSTM
  # converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS, tf.lite.OpsSet.SELECT_TF_OPS]
  # converter._experimental_lower_tensor_list_ops = False
  # tflite_model = converter.convert()

  # Save the model to disk
  # open("model.tflite", "wb").write(tflite_model)

  # Convert the model to the TensorFlow Lite format with quantization
  # converter = tf.lite.TFLiteConverter.from_keras_model(model)
  # converter.optimizations = [tf.lite.Optimize.DEFAULT]
  # only needed for LSTM
  # converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS, tf.lite.OpsSet.SELECT_TF_OPS]
  # converter._experimental_lower_tensor_list_ops = False
  # tflite_model = converter.convert()

  # Save the model to disk
  # open("model_quantized.tflite", "wb").write(tflite_model)

  # basic_model_size = os.path.getsize("model.tflite")
  # print("Basic model is %d bytes" % basic_model_size)
  # quantized_model_size = os.path.getsize("model_quantized.tflite")
  # print("Quantized model is %d bytes" % quantized_model_size)
  # difference = basic_model_size - quantized_model_size
  # print("Difference is %d bytes" % difference)


if __name__ == "__main__":
  parser = argparse.ArgumentParser()
  parser.add_argument("--model", "-m")
  parser.add_argument("--person", "-p")
  args = parser.parse_args()

  seq_length = 199

  print("Start to load data...")
  if args.person == "true":
    train_len, train_data, valid_len, valid_data, test_len, test_data = \
        load_data("./person_split/train", "./person_split/valid",
                  "./person_split/test", seq_length)
  else:
    train_len, train_data, valid_len, valid_data, test_len, test_data = \
        load_data("./data/train", "./data/valid", "./data/test", seq_length)

  print("Start to build net...")
  model, model_path = build_net(args, seq_length)
  
  # layer_name = "2ndPooling"
  # intermediate_layer_model = tf.keras.Model(inputs=model.input, outputs=model.get_layer(layer_name).output)
  # # intermediate_output = intermediate_layer_model(np.transpose(np.linspace(1,199,199)))
  # input_array = np.linspace(1,199,199)
  # intermediate_output = intermediate_layer_model(tf.convert_to_tensor(input_array[None,:,None,None], dtype=tf.int64))
  
  # print(tf.convert_to_tensor(input_array[None,:None,None], dtype=tf.int64))
  # print(intermediate_output)

                         

  print("Start training...")
  for x in range(100):
    train_net(model, model_path, train_len, train_data, valid_len, valid_data,
              test_len, test_data, args.model)
    

  for i in range(100):
      print(f"Iteration {i+1}: Accuracy = {accuracies[i]}")
      print(f"Confusion Matrix:\n{conf_matrices[i]}\n")

  mean_value = statistics.mean(accuracies)
  std_deviation = statistics.stdev(accuracies)

  print(f"Mean: {mean_value}")
  print(f"Standard Deviation: {std_deviation}")


  print("Training finished!")
