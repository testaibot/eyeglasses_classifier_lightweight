import torch
import torchvision
import numpy as np
import argparse
from sklearn.metrics import f1_score
from torchvision import transforms, utils
from torch.utils.data import Subset, DataLoader, Dataset
from typing import Tuple, List, Iterable
from image_folder import ImageFolderWithPaths
from avg_meter import AverageMeter
from stop_criteria import StopCriteria


TRAIN_SAMPLES_FRACTION = .8 # fraction of train samples to total number of samples

NORMALIZITAION_FOR_PRETRAINED = transforms.Normalize(
    mean=[0.485, 0.456, 0.406],
    std=[0.229, 0.224, 0.225]
)

def parse_args():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description='Script to train'
    )
    parser.add_argument('--epochs', type=int, help='Epochs number', default=1)
    parser.add_argument('--batch-size', type=int, help='Batch size', default=10)
    parser.add_argument('--images-path', type=str, help='Images directory location', required=True)
    parser.add_argument('--lr', type=float, help='Learning rate', default=1e-5)

    args = parser.parse_args()
    return args


def _mk_k_folds_indicies(arr: List[int], k: int) -> Iterable[Tuple[List[int], List[int]]]:
    ''' split list of integers up to "k" pairs that will form the base of k-fold partitions of dataset'''
    def array_diff(a1, a2):
        return list(filter(lambda v: len(list(filter(lambda x: x == v, a2))) == 0, a1))
    splited = np.array_split(arr, k)
    return [(array_diff(arr, s.tolist()), s.tolist()) for s in splited]

def mk_k_folds(ds: Dataset, k: int, batch_size: int) -> Iterable[Tuple[DataLoader, DataLoader]]:
    ''' make k-folds. returns Iterator (Train data, Validation data)'''
    indices = list(range(0, len(ds)))
    np.random.shuffle(indices)
    splited = _mk_k_folds_indicies(indices, k)
    mk_data_loader = lambda idxs: DataLoader(Subset(ds, idxs), batch_size, num_workers=0)
    return [(mk_data_loader(train_idxs), mk_data_loader(val_idxs)) for (train_idxs, val_idxs) in splited]
    


def train_cycle(
    data_loader: DataLoader, 
    model: torch.nn.Module, 
    optimizer: torch.optim.Optimizer, 
    device, 
    backprop=True) -> Tuple[float, float]:
    ''' regular single training/validation cycle '''
    avg_meter = AverageMeter()
    score = 0
    targets = []
    ys = []
    for *batch, _ in data_loader:
        x = batch[0].to(device)
        target = batch[1].to(device).float()
        y = model(x).squeeze(1)
        y_sigm = torch.sigmoid(y).cpu()
        targets = np.concatenate((targets, target.cpu().numpy()))
        ys = np.concatenate((ys, torch.sign(torch.where(y_sigm > 0.5, y_sigm, torch.tensor(.0))).detach().numpy()))
        if backprop: optimizer.zero_grad()
        loss_fn = torch.nn.BCEWithLogitsLoss()
        loss = loss_fn(y, target)
        
        if backprop:
            loss.backward()
            optimizer.step()
        avg_meter.update(loss.item(), len(batch))
    
    score = f1_score(targets, ys)
    return avg_meter.avg, score

if __name__ == '__main__':
    args = parse_args()
    print(args)
    MAX_EPOCH = args.epochs
    BATCH_SIZE = args.batch_size
    LR = args.lr
    np.random.seed(17)
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    print("Device", device)
   

    # ============ Data preparation ==============
    
    transform = transforms.Compose([
        transforms.ToTensor(),
        NORMALIZITAION_FOR_PRETRAINED
    ])
    images = ImageFolderWithPaths(args.images_path, transform=transform)

    
    folds = mk_k_folds(images, k=5, batch_size=BATCH_SIZE)
    
    
    # ============ SqueezeNet Regular Training =================
    
    print('SqueezeNet Regular Training ...')
    fold_scores = []
    for fold_n, (train_loader, val_loader) in enumerate(folds):
        print(f'Start fold #{fold_n + 1} ...')
        print(f'Train is {len(train_loader) * BATCH_SIZE} length')
        print(f'Val   is {len(val_loader) * BATCH_SIZE} length')
        model = torchvision.models.squeezenet1_1(pretrained=False, num_classes = 1)

        model.to(device)
        optimizer = torch.optim.Adam(model.parameters(), lr=LR)
        stop_criteria = StopCriteria()
        for epoch in range(0, MAX_EPOCH):
            model.train()
            avg_loss, score = train_cycle(train_loader, model, optimizer, device)
            print(epoch, 'TRAIN', round(avg_loss, 3), round(score, 3))
            model.eval()
            with torch.no_grad():
                avg_loss, score = train_cycle(val_loader, model, optimizer, device, backprop=False)
            print(epoch, 'VAL  ', round(avg_loss, 3), round(score, 3)) 
            if stop_criteria.check(round(avg_loss, 4), round(score, 4), model):
                print("Stop training. Score hasn't not improve.")
                torch.save(stop_criteria.get_best_model_params(), './squeezenet_params')
                break
        print("Best score is", round(stop_criteria.best_score, 3))
        fold_scores.append(stop_criteria.best_score)
        torch.save(stop_criteria.get_best_model_params(), './squeezenet_params')
        
    print(f'E[score] = {round(np.mean(fold_scores), 3)}, Var[score] = {round(np.std(fold_scores), 3)}')
