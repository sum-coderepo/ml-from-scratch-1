import os
import requests
import gzip
import shutil
import numpy as np
try:
    import matplotlib.pyplot as plt
except ImportError:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

from sklearn.preprocessing import OneHotEncoder
from sklearn.metrics import classification_report, confusion_matrix, precision_recall_fscore_support
from tqdm import tqdm
from .cifar10_lib import get_file, load_batch
from mpl_toolkits.axes_grid1 import ImageGrid


def load_dataset_mnist(check_path):
    print("-------> Downloading MNIST dataset")
    download_files = ["http://yann.lecun.com/exdb/mnist/train-images-idx3-ubyte.gz",
                      "http://yann.lecun.com/exdb/mnist/t10k-images-idx3-ubyte.gz",
                      "http://yann.lecun.com/exdb/mnist/train-labels-idx1-ubyte.gz",
                      "http://yann.lecun.com/exdb/mnist/t10k-labels-idx1-ubyte.gz"]
    check_path = os.path.abspath(check_path)

    if "data_mnist" not in os.listdir(check_path):
        os.mkdir(check_path + "/data_mnist")

    for file_url in download_files:
        file_name = file_url.split("/")[-1]
        uncompressed_file_name = "".join(file_name.split(".")[:-1])
        if uncompressed_file_name in os.listdir(check_path + "/data_mnist"):
            continue
        abs_path = check_path + "/data_mnist"
        if file_name not in os.listdir(check_path + "/data_mnist"):
            with open(abs_path + "/" + file_name, "wb") as f:
                r = requests.get(file_url)
                f.write(r.content)
        with gzip.open(abs_path + "/" + file_name, 'rb') as f_in:
            with open(abs_path + "/" + uncompressed_file_name, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        os.system("rm -rf " + file_name)

    print("-------> Finish")


def plot_image(image):
    image = np.array(image)
    image = image.reshape((28, 28))
    plt.imshow(image)
    plt.show()


def one_hot_encoding(y):
    one_hot = OneHotEncoder()
    y = y.reshape((-1, 1))
    return one_hot.fit_transform(y).toarray()


def preprocess_data(X, y, nn=False, test=False):
    X = np.array(X)
    X = X/255
    y = np.array(y)

    if nn:
        X = X.reshape((-1, 28, 28, 1))
    if not test:
        y = one_hot_encoding(y)
    return X, y

def save_grid_images(images, iteration):
    images = np.reshape(images, newshape=(-1, 28, 28))
    fig = plt.figure(figsize=(4., 4.))
    grid = ImageGrid(fig, 111,  # similar to subplot(111)
                    nrows_ncols=(4, 4),  # creates 2x2 grid of axes
                    axes_pad=0.1,  # pad between axes in inch.
                    )

    for ax, im in zip(grid, images):
        # Iterating over the grid returns the Axes.
        ax.imshow(im, cmap="gray")

    path = os.path.abspath(".")
    f = "gan-%d.png" % iteration
    plt.savefig(f)
    print("Image saved: %s" % os.path.join(path, f))


class Trainer:
    
    def __init__(self, model, batch_size, epochs):
        """
        Parameters
        ----------
        model: (object) the model uses to train.
        batch_size: (int) number of batch size.
        epochs: (int) number of training epochs.
        """
        self.model = model
        self.batch_size = batch_size
        self.epochs = epochs
        
    def train(self, X_train, y_train):
        m = X_train.shape[0]

        for e in range(self.epochs):
            indices = np.random.permutation(m)
            X_train = X_train[indices]
            y_train = y_train[indices]
            epoch_loss = 0.0
            num_batches = 0
            pbar = tqdm(range(0, X_train.shape[0], self.batch_size), desc="Epoch " + str(e+1))

            for it in pbar:
                X_batch = X_train[it:it+self.batch_size]
                y_batch = y_train[it:it+self.batch_size]
                
                y_hat = self.model(X_batch)
                batch_loss = self.model.loss_func(y_hat, y_batch)
                self.model.backward(y_batch, y_hat, X_batch)

                epoch_loss += batch_loss
                num_batches += 1
                pbar.set_description("Epoch " + str(e+1) + " - Loss: %.5f" % (epoch_loss/num_batches))
        
            print("Loss at epoch %d: %.5f" % (e+1, epoch_loss/num_batches))

    def save_model(self, name):
        import pickle
        with open(name, "wb") as f:
            pickle.dump(self.model, f, pickle.HIGHEST_PROTOCOL)

class TrainerGAN:

    def __init__(self, generator, discriminator, batch_size, iterations, latent_dim=100, k=1, report_freq=40):
        self.generator = generator
        self.discriminator = discriminator
        self.batch_size = batch_size
        self.iterations = iterations
        self.latent_dim = latent_dim
        self.k = k
        self.report_freq = report_freq

    def train(self, X_train):
        m = X_train.shape[0]
        ones = np.ones(shape=(self.batch_size, 1))
        zeros = np.zeros(shape=(self.batch_size, 1))
        y = np.concatenate((ones, zeros), axis=0)
        for i in range(self.iterations):
            z = np.random.normal(size=(self.batch_size, self.latent_dim))
            G = self.generator(z)
            report_loss = 0.0

            for _ in range(self.k):
                ind = np.random.choice(m, self.batch_size)
                x = X_train[ind]
                x = np.concatenate((x, G), axis=0)

                y_hat = self.discriminator(x)
                D_loss = self.discriminator.loss_func(y_hat, y)
                self.discriminator.backward(y, y_hat, x)
                report_loss += D_loss

            y_hat = self.discriminator(G)
            G_loss = self.discriminator.loss_func(y_hat, ones)
            self.generator.backward(ones, y_hat, z, self.discriminator)
            if (i+1)%self.report_freq == 0:
                print("[Iteration: %d] - [D loss: %.5f] - [G loss: %.5f]" % (i+1, D_loss/self.k, G_loss))

                z = np.random.normal(size=(self.batch_size, self.latent_dim))
                G = self.generator(z, prediction=True)
                save_grid_images(G, i+1)

class Evaluator:
    
    def __init__(self, model, loss_func):
        self.model = model
        self.loss_func = loss_func
    
    def evaluate(self, X_test, y_test):
        print("-"*50)
        y_pred = self.model.predict(X_test)
        loss = self.loss_func(self.model(X_test), y_test)
        print("Testing Loss: %.5f" % loss)
        conf_mat = confusion_matrix(y_test, y_pred)
        print(conf_mat)


def load_dataset_cifar10():
    """Loads CIFAR10 dataset.

    # Returns
        Tuple of Numpy arrays: `(x_train, y_train), (x_test, y_test)`.
    """
    dirname = 'cifar-10-batches-py'
    origin = 'https://www.cs.toronto.edu/~kriz/cifar-10-python.tar.gz'
    path = get_file(dirname, origin=origin, untar=True)

    num_train_samples = 50000

    x_train = np.empty((num_train_samples, 3, 32, 32), dtype='uint8')
    y_train = np.empty((num_train_samples,), dtype='uint8')

    for i in range(1, 6):
        fpath = os.path.join(path, 'data_batch_' + str(i))
        (x_train[(i - 1) * 10000: i * 10000, :, :, :],
        y_train[(i - 1) * 10000: i * 10000]) = load_batch(fpath)

    fpath = os.path.join(path, 'test_batch')
    x_test, y_test = load_batch(fpath)

    y_train = np.reshape(y_train, (len(y_train), 1))
    y_test = np.reshape(y_test, (len(y_test), 1))

    return (x_train, y_train), (x_test, y_test)