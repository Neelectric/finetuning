import random
import json
import torch
import pandas as pd
import numpy as np


def change_box_label(
    tokenizer,
    num_samples,
    data_file,
    object_file,
    num_ents_or_ops,
    architecture,
    few_shot,
    alt_examples,
):
    with open(data_file) as f:
        data = [json.loads(line) for line in f]

    assert num_samples <= len(data)
    prompts, labels = [], []

    for i in range(num_samples):
        org_prompt = " ".join(data[i]["sentence"].split(" ")[:-1])
        prompts.append(org_prompt)
        label = data[i]["sentence"].split(" ")[-1][:-1]
        labels.append(tokenizer.encode(label)[1])

        new_prompt = org_prompt.replace(" 0", " 6")
        new_prompt = new_prompt.replace(" 1", " 4")
        new_prompt = new_prompt.replace(" 2", " 9")
        prompts.append(new_prompt)
        labels.append(tokenizer.encode(label)[1])

    input_tokens = tokenizer(prompts, padding=True, return_tensors="pt")
    last_token_indices = input_tokens["attention_mask"].sum(dim=1) - 1
    input_ids = input_tokens["input_ids"].tolist()
    last_token_indices = last_token_indices.tolist()
    output_ids = labels

    return input_ids, last_token_indices, output_ids


def shift_box_positions(
    tokenizer, num_samples, data_file, object_file, num_boxes, few_shot, alt_examples
):
    with open(data_file) as f:
        data = [json.loads(line) for line in f]

    assert num_samples <= len(data)
    prompts, labels = [], []

    for i in range(num_samples):
        org_prompt = " ".join(data[i]["sentence"].split(" ")[:-1])
        prompts.append(org_prompt)
        label = data[i]["sentence"].split(" ")[-1][:-1]
        labels.append(tokenizer.encode(label)[1])

        query = org_prompt.split(". ")[-1]
        clean_prompt = org_prompt.split(". ")[0]
        clean_prompt = clean_prompt.split(", ")
        new_prompt = []
        for seg_idx in range(len(clean_prompt)):
            new_prompt.append(clean_prompt[(seg_idx + 1) % num_boxes])
        new_prompt = ", ".join(new_prompt)
        prompts.append(new_prompt + ". " + query)
        labels.append(tokenizer.encode(label)[1])

    input_tokens = tokenizer(prompts, padding=True, return_tensors="pt")
    last_token_indices = input_tokens["attention_mask"].sum(dim=1) - 1
    input_ids = input_tokens["input_ids"].tolist()
    last_token_indices = last_token_indices.tolist()
    output_ids = labels

    return input_ids, last_token_indices, output_ids


def object_alignment_example_generator(
    tokenizer, num_samples, data_file, object_file, few_shot, alt_examples
):
    with open(data_file) as f:
        data = [json.loads(line) for line in f]

    objects = pd.read_csv(object_file)

    assert num_samples <= len(data)
    prompts, all_object_tokens, labels = [], [], []

    if alt_examples:
        priminig_examples = """Watch is in Box 0, nothing is in Box 1, bottle is in Box 2. Box 2 contains bottle.\n Wire is in Box 0, biscotti is in Box 1, camera is in Box 2. Box 1 contains biscotti.\n Nothing is in Box 0, tetrapod is in Box 1, incense is in Box 2. Box 0 contains nothing.\n """
    else:
        priminig_examples = ""

    for i in range(num_samples):
        # Example with original object
        label = data[i]["sentence"].split(" ")[-1][:-1]
        # 0th index will be BOS token for llama-like tokenizer
        labels.append(tokenizer.encode(label)[1])

        object_index_in_segment = 0 if alt_examples else 3
        all_objects = [
            segment.split(" ")[object_index_in_segment].lower()
            for segment in data[i]["sentence"].split(".")[0].split(", ")
        ]
        all_object_tokens.append([tokenizer.encode(obj)[1] for obj in all_objects])

        org_prompt = " ".join(data[i]["sentence"].split(" ")[:-1])
        prompt = priminig_examples + org_prompt if few_shot else org_prompt
        prompts.append(prompt)

        # Example with random object
        box_num = org_prompt.split(". ")[-1].split(" ")[1]
        query = org_prompt.split(". ")[-1]
        clean_prompt = org_prompt.split(". ")[0]
        object = (
            clean_prompt.split(", ")[int(box_num)].split(" ")[0]
            if alt_examples
            else clean_prompt.split(", ")[int(box_num)].split(" ")[-1]
        )
        random_object = random.choice(objects["object_name"].tolist())

        # Capitalizing the first letter of the object
        if alt_examples and int(box_num) == 0:
            random_object = random_object[0].upper() + random_object[1:]

        clean_prompt = (
            ", ".join(clean_prompt.split(", ")[: int(box_num)])
            + (", " if int(box_num) != 0 else "")
            + clean_prompt.split(", ")[int(box_num)].replace(object, random_object, 1)
            + (", " if int(box_num) != len(clean_prompt.split(", ")) - 1 else "")
            + ", ".join(clean_prompt.split(", ")[int(box_num) + 1 :])
        )

        prompt = (
            priminig_examples + clean_prompt + ". " + query
            if few_shot
            else clean_prompt + ". " + query
        )

        prompts.append(prompt)
        labels.append(tokenizer.encode(random_object.lower())[1])
        all_objects = [random_object if obj == object else obj for obj in all_objects]
        all_object_tokens.append([tokenizer.encode(obj)[1] for obj in all_objects])

    input_tokens = tokenizer(prompts, padding=True, return_tensors="pt")
    last_token_indices = input_tokens["attention_mask"].sum(dim=1) - 1
    output_ids = torch.tensor(labels)

    # output_ids = torch.ones_like(input_tokens["input_ids"]) * -100

    # for bi in range(len(last_token_indices)):
    #     if bi % 2 == 0:
    #         output_ids[bi, last_token_indices[bi]] = torch.tensor(labels[bi])
    #     else:
    #         # For random object example, the output should be at the last token index of the original example
    #         output_ids[bi, last_token_indices[bi - 1]] = torch.tensor(labels[bi])

    input_ids = input_tokens["input_ids"].tolist()
    last_token_indices = last_token_indices.tolist()
    output_ids = output_ids.tolist()

    return input_ids, last_token_indices, output_ids, all_object_tokens


def change_query_box_pos(
    tokenizer,
    num_samples,
    data_file,
    object_file,
    num_ents_or_ops,
    architecture,
    few_shot,
    alt_examples,
):
    input_ids, last_token_indices, output_ids = change_box_label(
        tokenizer,
        num_samples,
        data_file,
        object_file,
        num_ents_or_ops,
        architecture,
        few_shot,
        alt_examples,
    )

    all_base_input_ids = []
    all_base_input_last_pos = []
    all_source_input_ids = []
    all_source_input_last_pos = []
    all_ctf_output_ids = []

    for i in range(0, num_samples, 2):
        all_base_input_ids += [input_ids[i]]
        all_base_input_last_pos += [last_token_indices[i]]
        all_source_input_ids += [input_ids[i + 1]]
        all_source_input_last_pos += [last_token_indices[i + 1]]
        all_ctf_output_ids += [output_ids[i]]

    return (
        all_base_input_ids,
        all_base_input_last_pos,
        all_source_input_ids,
        all_source_input_last_pos,
        all_ctf_output_ids,
    )


def shift_query_position_example_sampler(
    tokenizer,
    num_samples,
    data_file,
    object_file,
    num_ents_or_ops,
    architecture,
    few_shot,
    alt_examples,
):
    input_ids, last_token_indices, output_ids = shift_box_positions(
        tokenizer,
        num_samples,
        data_file,
        object_file,
        num_ents_or_ops,
        few_shot,
        alt_examples,
    )

    all_base_input_ids = []
    all_base_input_last_pos = []
    all_source_input_ids = []
    all_source_input_last_pos = []
    all_ctf_output_ids = []

    for i in range(0, num_samples, 2):
        all_base_input_ids += [input_ids[i]]
        all_base_input_last_pos += [last_token_indices[i]]
        all_source_input_ids += [input_ids[i + 1]]
        all_source_input_last_pos += [last_token_indices[i + 1]]
        all_ctf_output_ids += [output_ids[i]]

    return (
        all_base_input_ids,
        all_base_input_last_pos,
        all_source_input_ids,
        all_source_input_last_pos,
        all_ctf_output_ids,
    )


def get_data_for_mean_ablation(
    tokenizer,
    num_samples,
    data_file,
    num_boxes,
):
    """
    This function returns the data for the mean ablation experiment,
    which consists of examples with different set of objects, box
    labels and randomly selected query box label.

    Args:
        tokenizer (transformers.tokenizer): Tokenizer object
        num_samples (int): Number of samples to generate
        data_file (str): Path to the data file
        num_boxes (int): Number of boxes in the scene
    """

    with open(data_file, encoding="utf-8") as file_handle:
        data = [json.loads(line) for line in file_handle]

    assert num_samples <= len(data)
    prompts = []

    # Each prompt will have different set of objects and box labels,
    # with random query box label
    for i in range(0, num_samples, num_boxes):
        prompt = " ".join(data[i]["sentence"].split(" ")[:-1])
        prompt_query = prompt.split(". ", maxsplit=1)[-1]
        random_alphabet = chr(random.randint(65, 90))
        prompt_query = (
            prompt_query.split(" ")[0]
            + " "
            + random_alphabet
            + " "
            + " ".join(prompt_query.split(" ")[2:])
        )
        prompt = prompt.split(". ", maxsplit=1)[0] + ". " + prompt_query
        prompts.append(prompt)

    input_tokens = tokenizer(prompts, padding=True, return_tensors="pt")
    last_token_indices = input_tokens["attention_mask"].sum(dim=1) - 1

    return (
        input_tokens["input_ids"],
        last_token_indices,
    )


def alter_box_object_association(
    tokenizer,
    num_samples,
    data_file,
):
    with open(data_file) as f:
        data = [json.loads(line) for line in f]

    assert num_samples <= len(data)
    base_prompts, source_prompts, labels = [], [], []

    for i in range(0, num_samples):
        base_prompt = " ".join(data[i]["sentence"].split(" ")[:-1])
        base_query = base_prompt.split(". ")[-1]
        base_query_box_label = base_query.split(" ")[1]
        base_query_box_pos = [
            idx
            for idx, segment in enumerate(base_query.split(". ")[0].split(", "))
            if base_query_box_label in segment
        ][0]
        if base_query_box_pos == -1:
            raise ValueError("Box label not found in the base prompt")
        base_prompts.append(base_prompt)

        source_query_box_pos = base_query_box_pos
        random_choices = list(range(0, num_samples))
        random.shuffle(random_choices)
        while source_query_box_pos == base_query_box_pos:
            random_source_index = random.choice(random_choices)
            source_prompt = " ".join(
                data[random_source_index]["sentence"].split(" ")[:-1]
            )
            source_query = source_prompt.split(". ")[-1]
            source_query_box_label = source_query.split(" ")[1]
            source_query_box_pos = [
                idx
                for idx, segment in enumerate(source_prompt.split(". ")[0].split(", "))
                if source_query_box_label in segment
            ][0]
            random_choices.remove(random_source_index)

        source_segment = source_prompt.split(". ")[0].split(", ")[source_query_box_pos]
        source_segment = source_segment.replace(" is in", " is not in")
        source_prompt = (
            ", ".join(source_prompt.split(". ")[0].split(", ")[:source_query_box_pos])
            + (", " if source_query_box_pos != 0 else "")
            + source_segment
            + (
                ", "
                if source_query_box_pos
                != len(source_prompt.split(". ")[0].split(", ")) - 1
                else ""
            )
            + ", ".join(
                source_prompt.split(". ")[0].split(", ")[source_query_box_pos + 1 :]
            )
            + ". "
            + source_prompt.split(". ")[-1]
        )
        source_prompts.append(source_prompt)

        base_prompt = base_prompt.split(". ")[0]
        correct_object = base_prompt.split(", ")[source_query_box_pos].split(" ")[1]
        labels.append(tokenizer.encode(correct_object)[1])

    base_input_tokens = tokenizer(base_prompts, padding=True, return_tensors="pt")[
        "input_ids"
    ]
    base_last_token_indices = (
        tokenizer(base_prompts, padding=True, return_tensors="pt")[
            "attention_mask"
        ].sum(dim=1)
        - 1
    )
    source_input_tokens = tokenizer(source_prompts, padding=True, return_tensors="pt")[
        "input_ids"
    ]
    source_last_token_indices = (
        tokenizer(source_prompts, padding=True, return_tensors="pt")[
            "attention_mask"
        ].sum(dim=1)
        - 1
    )
    output_ids = torch.tensor(labels)

    return (
        base_input_tokens,
        base_last_token_indices,
        source_input_tokens,
        source_last_token_indices,
        output_ids,
    )


def add_box_before_correct_segment(
    tokenizer,
    num_samples,
    data_file,
):
    with open(data_file) as f:
        data = [json.loads(line) for line in f]

    assert num_samples <= len(data)
    base_prompts, source_prompts, labels = [], [], []

    for i in range(0, num_samples):
        base_prompt = " ".join(data[i]["sentence"].split(" ")[:-1])
        base_query = base_prompt.split(". ")[-1]
        base_query_box_label = base_query.split(" ")[1]
        base_query_box_pos = [
            idx
            for idx, segment in enumerate(base_query.split(". ")[0].split(", "))
            if base_query_box_label in segment
        ][0]
        if base_query_box_pos == -1:
            raise ValueError("Box label not found in the base prompt")
        base_prompts.append(base_prompt)

        source_query_box_pos = base_query_box_pos
        random_choices = list(range(0, num_samples))
        random.shuffle(random_choices)
        while source_query_box_pos == base_query_box_pos:
            random_source_index = random.choice(random_choices)
            source_prompt = " ".join(
                data[random_source_index]["sentence"].split(" ")[:-1]
            )
            source_query = source_prompt.split(". ")[-1]
            source_query_box_label = source_query.split(" ")[1]
            source_query_box_pos = [
                idx
                for idx, segment in enumerate(source_prompt.split(". ")[0].split(", "))
                if source_query_box_label in segment
            ][0]
            random_choices.remove(random_source_index)

        source_segment = source_prompt.split(". ")[0].split(", ")[source_query_box_pos]
        if source_query_box_pos != 0:
            source_segment = (
                "there are three additional boxes, Box PP, Box BB and Box AA, "
                + source_segment
            )
        else:
            source_segment = (
                "There are three additional boxes, Box PP, Box BB and Box AA, "
                + source_segment
            )
        source_prompt = (
            ", ".join(source_prompt.split(". ")[0].split(", ")[:source_query_box_pos])
            + (", " if source_query_box_pos != 0 else "")
            + source_segment
            + (
                ", "
                if source_query_box_pos
                != len(source_prompt.split(". ")[0].split(", ")) - 1
                else ""
            )
            + ", ".join(
                source_prompt.split(". ")[0].split(", ")[source_query_box_pos + 1 :]
            )
            + ". "
            + source_prompt.split(". ")[-1]
        )
        source_prompts.append(source_prompt)

        base_prompt = base_prompt.split(". ")[0]
        correct_object = base_prompt.split(", ")[source_query_box_pos].split(" ")[1]
        labels.append(tokenizer.encode(correct_object)[1])

    base_input_tokens = tokenizer(base_prompts, padding=True, return_tensors="pt")[
        "input_ids"
    ]
    base_last_token_indices = (
        tokenizer(base_prompts, padding=True, return_tensors="pt")[
            "attention_mask"
        ].sum(dim=1)
        - 1
    )
    source_input_tokens = tokenizer(source_prompts, padding=True, return_tensors="pt")[
        "input_ids"
    ]
    source_last_token_indices = (
        tokenizer(source_prompts, padding=True, return_tensors="pt")[
            "attention_mask"
        ].sum(dim=1)
        - 1
    )
    output_ids = torch.tensor(labels)

    return (
        base_input_tokens,
        base_last_token_indices,
        source_input_tokens,
        source_last_token_indices,
        output_ids,
    )


def add_raw_text_at_end(
    tokenizer,
    num_samples,
    data_file,
):
    with open(data_file) as f:
        data = [json.loads(line) for line in f]

    assert num_samples <= len(data)
    base_prompts, source_prompts, labels = [], [], []

    for i in range(0, num_samples):
        base_prompt = " ".join(data[i]["sentence"].split(" ")[:-1])
        base_query = base_prompt.split(". ")[-1]
        base_query_box_label = base_query.split(" ")[1]
        base_query_box_pos = [
            idx
            for idx, segment in enumerate(base_query.split(". ")[0].split(", "))
            if base_query_box_label in segment
        ][0]
        if base_query_box_pos == -1:
            raise ValueError("Box label not found in the base prompt")
        base_prompts.append(base_prompt)

        source_query_box_pos = base_query_box_pos
        random_choices = list(range(0, num_samples))
        random.shuffle(random_choices)
        while source_query_box_pos == base_query_box_pos:
            random_source_index = random.choice(random_choices)
            source_prompt = " ".join(
                data[random_source_index]["sentence"].split(" ")[:-1]
            )
            source_query = source_prompt.split(". ")[-1]
            source_query_box_label = source_query.split(" ")[1]
            source_query_box_pos = [
                idx
                for idx, segment in enumerate(source_prompt.split(". ")[0].split(", "))
                if source_query_box_label in segment
            ][0]
            random_choices.remove(random_source_index)

        source_prompt = (
            source_prompt.split(". ")[0]
            + ", these are a bunch of boxes containing objects"
            + ". "
            + source_prompt.split(". ")[-1]
        )
        source_prompts.append(source_prompt)

        base_prompt = base_prompt.split(". ")[0]
        correct_object = base_prompt.split(", ")[source_query_box_pos].split(" ")[1]
        labels.append(tokenizer.encode(correct_object)[1])

    base_input_tokens = tokenizer(base_prompts, padding=True, return_tensors="pt")[
        "input_ids"
    ]
    base_last_token_indices = (
        tokenizer(base_prompts, padding=True, return_tensors="pt")[
            "attention_mask"
        ].sum(dim=1)
        - 1
    )
    source_input_tokens = tokenizer(source_prompts, padding=True, return_tensors="pt")[
        "input_ids"
    ]
    source_last_token_indices = (
        tokenizer(source_prompts, padding=True, return_tensors="pt")[
            "attention_mask"
        ].sum(dim=1)
        - 1
    )
    output_ids = torch.tensor(labels)

    return (
        base_input_tokens,
        base_last_token_indices,
        source_input_tokens,
        source_last_token_indices,
        output_ids,
    )


def add_raw_text_at_start(
    tokenizer,
    num_samples,
    data_file,
):
    with open(data_file) as f:
        data = [json.loads(line) for line in f]

    assert num_samples <= len(data)
    base_prompts, source_prompts, labels = [], [], []

    for i in range(0, num_samples):
        base_prompt = " ".join(data[i]["sentence"].split(" ")[:-1])
        base_query = base_prompt.split(". ")[-1]
        base_query_box_label = base_query.split(" ")[1]
        base_query_box_pos = [
            idx
            for idx, segment in enumerate(base_query.split(". ")[0].split(", "))
            if base_query_box_label in segment
        ][0]
        if base_query_box_pos == -1:
            raise ValueError("Box label not found in the base prompt")
        base_prompts.append(base_prompt)

        source_query_box_pos = base_query_box_pos
        random_choices = list(range(0, num_samples))
        random.shuffle(random_choices)
        while source_query_box_pos == base_query_box_pos:
            random_source_index = random.choice(random_choices)
            source_prompt = " ".join(
                data[random_source_index]["sentence"].split(" ")[:-1]
            )
            source_query = source_prompt.split(". ")[-1]
            source_query_box_label = source_query.split(" ")[1]
            source_query_box_pos = [
                idx
                for idx, segment in enumerate(source_prompt.split(". ")[0].split(", "))
                if source_query_box_label in segment
            ][0]
            random_choices.remove(random_source_index)

        source_prompt = (
            "There are a bunch of boxes containing objects, "
            + source_prompt[0].lower()
            + source_prompt[1:]
        )
        source_prompts.append(source_prompt)

        base_prompt = base_prompt.split(". ")[0]
        correct_object = base_prompt.split(", ")[source_query_box_pos].split(" ")[1]
        labels.append(tokenizer.encode(correct_object)[1])

    base_input_tokens = tokenizer(base_prompts, padding=True, return_tensors="pt")[
        "input_ids"
    ]
    base_last_token_indices = (
        tokenizer(base_prompts, padding=True, return_tensors="pt")[
            "attention_mask"
        ].sum(dim=1)
        - 1
    )
    source_input_tokens = tokenizer(source_prompts, padding=True, return_tensors="pt")[
        "input_ids"
    ]
    source_last_token_indices = (
        tokenizer(source_prompts, padding=True, return_tensors="pt")[
            "attention_mask"
        ].sum(dim=1)
        - 1
    )
    output_ids = torch.tensor(labels)

    return (
        base_input_tokens,
        base_last_token_indices,
        source_input_tokens,
        source_last_token_indices,
        output_ids,
    )


def add_segment_at_end(
    tokenizer,
    num_samples,
    data_file,
):
    with open(data_file) as f:
        data = [json.loads(line) for line in f]

    assert num_samples <= len(data)
    base_prompts, source_prompts, labels = [], [], []

    for i in range(0, num_samples):
        base_prompt = " ".join(data[i]["sentence"].split(" ")[:-1])
        base_query = base_prompt.split(". ")[-1]
        base_query_box_label = base_query.split(" ")[1]
        base_query_box_pos = [
            idx
            for idx, segment in enumerate(base_query.split(". ")[0].split(", "))
            if base_query_box_label in segment
        ][0]
        if base_query_box_pos == -1:
            raise ValueError("Box label not found in the base prompt")
        base_prompts.append(base_prompt)

        source_query_box_pos = base_query_box_pos
        random_choices = list(range(0, num_samples))
        random.shuffle(random_choices)
        while source_query_box_pos == base_query_box_pos:
            random_source_index = random.choice(random_choices)
            source_prompt = " ".join(
                data[random_source_index]["sentence"].split(" ")[:-1]
            )
            source_query = source_prompt.split(". ")[-1]
            source_query_box_label = source_query.split(" ")[1]
            source_query_box_pos = [
                idx
                for idx, segment in enumerate(source_prompt.split(". ")[0].split(", "))
                if source_query_box_label in segment
            ][0]
            random_choices.remove(random_source_index)

        source_prompt = (
            source_prompt.split(". ")[0]
            + ", the apple is in Box O"
            + ". "
            + source_prompt.split(". ")[-1]
        )
        source_prompts.append(source_prompt)

        base_prompt = base_prompt.split(". ")[0]
        correct_object = base_prompt.split(", ")[source_query_box_pos].split(" ")[1]
        labels.append(tokenizer.encode(correct_object)[1])

    base_input_tokens = tokenizer(base_prompts, padding=True, return_tensors="pt")[
        "input_ids"
    ]
    base_last_token_indices = (
        tokenizer(base_prompts, padding=True, return_tensors="pt")[
            "attention_mask"
        ].sum(dim=1)
        - 1
    )
    source_input_tokens = tokenizer(source_prompts, padding=True, return_tensors="pt")[
        "input_ids"
    ]
    source_last_token_indices = (
        tokenizer(source_prompts, padding=True, return_tensors="pt")[
            "attention_mask"
        ].sum(dim=1)
        - 1
    )
    output_ids = torch.tensor(labels)

    return (
        base_input_tokens,
        base_last_token_indices,
        source_input_tokens,
        source_last_token_indices,
        output_ids,
    )


def add_segment_at_start(
    tokenizer,
    num_samples,
    data_file,
):
    with open(data_file) as f:
        data = [json.loads(line) for line in f]

    assert num_samples <= len(data)
    base_prompts, source_prompts, labels = [], [], []

    for i in range(0, num_samples):
        base_prompt = " ".join(data[i]["sentence"].split(" ")[:-1])
        base_query = base_prompt.split(". ")[-1]
        base_query_box_label = base_query.split(" ")[1]
        base_query_box_pos = [
            idx
            for idx, segment in enumerate(base_query.split(". ")[0].split(", "))
            if base_query_box_label in segment
        ][0]
        if base_query_box_pos == -1:
            raise ValueError("Box label not found in the base prompt")
        base_prompts.append(base_prompt)

        source_query_box_pos = base_query_box_pos
        random_choices = list(range(0, num_samples))
        random.shuffle(random_choices)
        while source_query_box_pos == base_query_box_pos:
            random_source_index = random.choice(random_choices)
            source_prompt = " ".join(
                data[random_source_index]["sentence"].split(" ")[:-1]
            )
            source_query = source_prompt.split(". ")[-1]
            source_query_box_label = source_query.split(" ")[1]
            source_query_box_pos = [
                idx
                for idx, segment in enumerate(source_prompt.split(". ")[0].split(", "))
                if source_query_box_label in segment
            ][0]
            random_choices.remove(random_source_index)

        source_prompt = (
            "The apple is in Box O, " + source_prompt[0].lower() + source_prompt[1:]
        )
        source_prompts.append(source_prompt)

        base_prompt = base_prompt.split(". ")[0]
        correct_object = base_prompt.split(", ")[source_query_box_pos].split(" ")[1]
        labels.append(tokenizer.encode(correct_object)[1])

    base_input_tokens = tokenizer(base_prompts, padding=True, return_tensors="pt")[
        "input_ids"
    ]
    base_last_token_indices = (
        tokenizer(base_prompts, padding=True, return_tensors="pt")[
            "attention_mask"
        ].sum(dim=1)
        - 1
    )
    source_input_tokens = tokenizer(source_prompts, padding=True, return_tensors="pt")[
        "input_ids"
    ]
    source_last_token_indices = (
        tokenizer(source_prompts, padding=True, return_tensors="pt")[
            "attention_mask"
        ].sum(dim=1)
        - 1
    )
    output_ids = torch.tensor(labels)

    return (
        base_input_tokens,
        base_last_token_indices,
        source_input_tokens,
        source_last_token_indices,
        output_ids,
    )


def additional_token_btw_box_and_object(
    tokenizer,
    num_samples,
    data_file,
):
    with open(data_file) as f:
        data = [json.loads(line) for line in f]

    assert num_samples <= len(data)
    base_prompts, source_prompts, labels = [], [], []

    for i in range(0, num_samples):
        base_prompt = " ".join(data[i]["sentence"].split(" ")[:-1])
        base_query = base_prompt.split(". ")[-1]
        base_query_box_label = base_query.split(" ")[1]
        base_query_box_pos = [
            idx
            for idx, segment in enumerate(base_query.split(". ")[0].split(", "))
            if base_query_box_label in segment
        ][0]
        if base_query_box_pos == -1:
            raise ValueError("Box label not found in the base prompt")
        base_prompts.append(base_prompt)

        source_query_box_pos = base_query_box_pos
        random_choices = list(range(0, num_samples))
        random.shuffle(random_choices)
        while source_query_box_pos == base_query_box_pos:
            random_source_index = random.choice(random_choices)
            source_prompt = " ".join(
                data[random_source_index]["sentence"].split(" ")[:-1]
            )
            source_query = source_prompt.split(". ")[-1]
            source_query_box_label = source_query.split(" ")[1]
            source_query_box_pos = [
                idx
                for idx, segment in enumerate(source_prompt.split(". ")[0].split(", "))
                if source_query_box_label in segment
            ][0]
            random_choices.remove(random_source_index)

        source_segment = source_prompt.split(". ")[0].split(", ")[source_query_box_pos]
        source_segment = source_segment.replace(" is in", " is contained in the")
        source_prompt = (
            ", ".join(source_prompt.split(". ")[0].split(", ")[:source_query_box_pos])
            + (", " if source_query_box_pos != 0 else "")
            + source_segment
            + (
                ", "
                if source_query_box_pos
                != len(source_prompt.split(". ")[0].split(", ")) - 1
                else ""
            )
            + ", ".join(
                source_prompt.split(". ")[0].split(", ")[source_query_box_pos + 1 :]
            )
            + ". "
            + source_prompt.split(". ")[-1]
        )
        source_prompts.append(source_prompt)

        base_prompt = base_prompt.split(". ")[0]
        correct_object = base_prompt.split(", ")[source_query_box_pos].split(" ")[1]
        labels.append(tokenizer.encode(correct_object)[1])

    base_input_tokens = tokenizer(base_prompts, padding=True, return_tensors="pt")[
        "input_ids"
    ]
    base_last_token_indices = (
        tokenizer(base_prompts, padding=True, return_tensors="pt")[
            "attention_mask"
        ].sum(dim=1)
        - 1
    )
    source_input_tokens = tokenizer(source_prompts, padding=True, return_tensors="pt")[
        "input_ids"
    ]
    source_last_token_indices = (
        tokenizer(source_prompts, padding=True, return_tensors="pt")[
            "attention_mask"
        ].sum(dim=1)
        - 1
    )
    output_ids = torch.tensor(labels)

    return (
        base_input_tokens,
        base_last_token_indices,
        source_input_tokens,
        source_last_token_indices,
        output_ids,
    )


def diff_index_query_box(
    tokenizer,
    num_samples,
    data_file,
):
    with open(data_file) as f:
        data = [json.loads(line) for line in f]

    assert num_samples <= len(data)
    base_prompts, source_prompts, labels = [], [], []

    for i in range(0, num_samples):
        base_prompt = " ".join(data[i]["sentence"].split(" ")[:-1])
        base_query = base_prompt.split(". ")[-1]
        base_query_box_label = base_query.split(" ")[1]
        base_query_box_pos = [
            idx
            for idx, segment in enumerate(base_query.split(". ")[0].split(", "))
            if base_query_box_label in segment
        ][0]
        if base_query_box_pos == -1:
            raise ValueError("Box label not found in the base prompt")
        base_prompts.append(base_prompt)

        source_query_box_pos = base_query_box_pos
        random_choices = list(range(0, num_samples))
        random.shuffle(random_choices)
        while source_query_box_pos == base_query_box_pos:
            random_source_index = random.choice(random_choices)
            source_prompt = " ".join(
                data[random_source_index]["sentence"].split(" ")[:-1]
            )
            source_query = source_prompt.split(". ")[-1]
            source_query_box_label = source_query.split(" ")[1]
            source_query_box_pos = [
                idx
                for idx, segment in enumerate(source_prompt.split(". ")[0].split(", "))
                if source_query_box_label in segment
            ][0]
            random_choices.remove(random_source_index)

        source_prompts.append(source_prompt)

        base_prompt = base_prompt.split(". ")[0]
        correct_object = base_prompt.split(", ")[(source_query_box_pos + 1) % 7].split(
            " "
        )[1]
        labels.append(tokenizer.encode(correct_object)[1])

    base_input_tokens = tokenizer(base_prompts, padding=True, return_tensors="pt")[
        "input_ids"
    ]
    base_last_token_indices = (
        tokenizer(base_prompts, padding=True, return_tensors="pt")[
            "attention_mask"
        ].sum(dim=1)
        - 1
    )
    source_input_tokens = tokenizer(source_prompts, padding=True, return_tensors="pt")[
        "input_ids"
    ]
    source_last_token_indices = (
        tokenizer(source_prompts, padding=True, return_tensors="pt")[
            "attention_mask"
        ].sum(dim=1)
        - 1
    )
    output_ids = torch.tensor(labels)

    return (
        base_input_tokens,
        base_last_token_indices,
        source_input_tokens,
        source_last_token_indices,
        output_ids,
    )


def box_object_altered_order(
    tokenizer,
    num_samples,
    data_file,
):
    with open(data_file) as f:
        data = [json.loads(line) for line in f]

    # data = [data[i] for i in correct_pred_indices]

    assert num_samples <= len(data)
    base_prompts, source_prompts, labels = [], [], []

    for i in range(0, num_samples):
        base_prompt = " ".join(data[i]["sentence"].split(" ")[:-1])
        base_query = base_prompt.split(". ")[-1]
        base_query_box_label = base_query.split(" ")[1]
        base_query_box_pos = [
            idx
            for idx, segment in enumerate(base_query.split(". ")[0].split(", "))
            if base_query_box_label in segment
        ][0]
        if base_query_box_pos == -1:
            raise ValueError("Box label not found in the base prompt")
        base_prompts.append(base_prompt)

        source_query_box_pos = base_query_box_pos
        random_choices = list(range(0, num_samples))
        random.shuffle(random_choices)
        while source_query_box_pos == base_query_box_pos:
            random_source_index = random.choice(random_choices)
            source_prompt = " ".join(
                data[random_source_index]["sentence"].split(" ")[:-1]
            )
            source_query = source_prompt.split(". ")[-1]
            source_query_box_label = source_query.split(" ")[1]
            source_query_box_pos = [
                idx
                for idx, segment in enumerate(source_prompt.split(". ")[0].split(", "))
                if source_query_box_label in segment
            ][0]
            random_choices.remove(random_source_index)

        source_segment = source_prompt.split(". ")[0].split(", ")[source_query_box_pos]
        source_box = source_segment.split(" ")[-1]
        source_object = source_segment.split(" ")[1]
        source_segment = f"Box {source_box} contains the {source_object}"

        source_prompt = (
            ", ".join(source_prompt.split(". ")[0].split(", ")[:source_query_box_pos])
            + ", "
            + source_segment
            + ", "
            + ", ".join(
                source_prompt.split(". ")[0].split(", ")[source_query_box_pos + 1 :]
            )
            + ". "
            + source_prompt.split(". ")[-1]
        )

        source_prompts.append(source_prompt)

        base_prompt = base_prompt.split(". ")[0]
        correct_object = base_prompt.split(", ")[source_query_box_pos].split(" ")[1]
        labels.append(tokenizer.encode(correct_object)[1])

    base_input_tokens = tokenizer(base_prompts, padding=True, return_tensors="pt")[
        "input_ids"
    ]
    base_last_token_indices = (
        tokenizer(base_prompts, padding=True, return_tensors="pt")[
            "attention_mask"
        ].sum(dim=1)
        - 1
    )
    source_input_tokens = tokenizer(source_prompts, padding=True, return_tensors="pt")[
        "input_ids"
    ]
    source_last_token_indices = (
        tokenizer(source_prompts, padding=True, return_tensors="pt")[
            "attention_mask"
        ].sum(dim=1)
        - 1
    )
    output_ids = torch.tensor(labels)

    return (
        base_input_tokens,
        base_last_token_indices,
        source_input_tokens,
        source_last_token_indices,
        output_ids,
    )


def add_comma_after_object(
    tokenizer,
    num_samples,
    data_file,
):
    with open(data_file) as f:
        data = [json.loads(line) for line in f]

    # data = [data[i] for i in correct_pred_indices]

    assert num_samples <= len(data)
    base_prompts, source_prompts, labels = [], [], []

    for i in range(0, num_samples):
        base_prompt = " ".join(data[i]["sentence"].split(" ")[:-1])
        base_query = base_prompt.split(". ")[-1]
        base_query_box_label = base_query.split(" ")[1]
        base_query_box_pos = [
            idx
            for idx, segment in enumerate(base_query.split(". ")[0].split(", "))
            if base_query_box_label in segment
        ][0]
        if base_query_box_pos == -1:
            raise ValueError("Box label not found in the base prompt")
        base_prompts.append(base_prompt)

        source_query_box_pos = base_query_box_pos
        random_choices = list(range(0, num_samples))
        random.shuffle(random_choices)
        while source_query_box_pos == base_query_box_pos:
            random_source_index = random.choice(random_choices)
            source_prompt = " ".join(
                data[random_source_index]["sentence"].split(" ")[:-1]
            )
            source_query = source_prompt.split(". ")[-1]
            source_query_box_label = source_query.split(" ")[1]
            source_query_box_pos = [
                idx
                for idx, segment in enumerate(source_prompt.split(". ")[0].split(", "))
                if source_query_box_label in segment
            ][0]
            random_choices.remove(random_source_index)

        source_prompt = source_prompt.replace(" is", ", is")
        source_prompts.append(source_prompt)

        base_prompt = base_prompt.split(". ")[0]
        correct_object = base_prompt.split(", ")[source_query_box_pos].split(" ")[1]
        labels.append(tokenizer.encode(correct_object)[1])

    base_input_tokens = tokenizer(base_prompts, padding=True, return_tensors="pt")[
        "input_ids"
    ]
    base_last_token_indices = (
        tokenizer(base_prompts, padding=True, return_tensors="pt")[
            "attention_mask"
        ].sum(dim=1)
        - 1
    )
    source_input_tokens = tokenizer(source_prompts, padding=True, return_tensors="pt")[
        "input_ids"
    ]
    source_last_token_indices = (
        tokenizer(source_prompts, padding=True, return_tensors="pt")[
            "attention_mask"
        ].sum(dim=1)
        - 1
    )
    output_ids = torch.tensor(labels)

    return (
        base_input_tokens,
        base_last_token_indices,
        source_input_tokens,
        source_last_token_indices,
        output_ids,
    )


def remove_comma_desiderata(
    tokenizer,
    num_samples,
    data_file,
):
    with open(data_file) as f:
        data = [json.loads(line) for line in f]

    # data = [data[i] for i in correct_pred_indices]

    assert num_samples <= len(data)
    base_prompts, source_prompts, labels = [], [], []

    for i in range(0, num_samples):
        base_prompt = " ".join(data[i]["sentence"].split(" ")[:-1])
        base_query = base_prompt.split(". ")[-1]
        base_query_box_label = base_query.split(" ")[1]
        base_query_box_pos = [
            idx
            for idx, segment in enumerate(base_query.split(". ")[0].split(", "))
            if base_query_box_label in segment
        ][0]
        if base_query_box_pos == -1:
            raise ValueError("Box label not found in the base prompt")
        base_prompts.append(base_prompt)

        source_query_box_pos = base_query_box_pos
        random_choices = list(range(0, num_samples))
        random.shuffle(random_choices)
        while source_query_box_pos == base_query_box_pos:
            random_source_index = random.choice(random_choices)
            source_prompt = " ".join(
                data[random_source_index]["sentence"].split(" ")[:-1]
            )
            source_query = source_prompt.split(". ")[-1]
            source_query_box_label = source_query.split(" ")[1]
            source_query_box_pos = [
                idx
                for idx, segment in enumerate(source_prompt.split(". ")[0].split(", "))
                if source_query_box_label in segment
            ][0]
            random_choices.remove(random_source_index)

        source_prompt = source_prompt.replace(", ", " ")
        source_prompts.append(source_prompt)

        base_prompt = base_prompt.split(". ")[0]
        correct_object = base_prompt.split(", ")[source_query_box_pos].split(" ")[1]
        labels.append(tokenizer.encode(correct_object)[1])

    base_input_tokens = tokenizer(base_prompts, padding=True, return_tensors="pt")[
        "input_ids"
    ]
    base_last_token_indices = (
        tokenizer(base_prompts, padding=True, return_tensors="pt")[
            "attention_mask"
        ].sum(dim=1)
        - 1
    )
    source_input_tokens = tokenizer(source_prompts, padding=True, return_tensors="pt")[
        "input_ids"
    ]
    source_last_token_indices = (
        tokenizer(source_prompts, padding=True, return_tensors="pt")[
            "attention_mask"
        ].sum(dim=1)
        - 1
    )
    output_ids = torch.tensor(labels)

    return (
        base_input_tokens,
        base_last_token_indices,
        source_input_tokens,
        source_last_token_indices,
        output_ids,
    )


def box_label_value_desiderata(
    tokenizer,
    num_samples,
    data_file,
    correct_pred_indices,
    num_boxes,
    object_file,
    alt_format=True,
):
    with open(data_file) as f:
        data = [json.loads(line) for line in f]

    assert num_samples <= len(data)
    base_prompts, source_prompts, labels = [], [], []

    for i in range(0, num_samples):
        base_prompt = " ".join(data[i]["sentence"].split(" ")[:-1])
        base_query = base_prompt.split(". ")[-1]
        base_query_box_label = base_query.split(" ")[1]
        base_box_labels = [
            segment.split(" ")[-1] for segment in base_prompt.split(". ")[0].split(", ")
        ]
        base_prompts.append(base_prompt)

        random_choices = list(range(0, num_samples))
        random.shuffle(random_choices)
        while True:
            random_source_index = random.choice(random_choices)
            source_prompt = " ".join(
                data[random_source_index]["sentence"].split(" ")[:-1]
            )
            source_query = source_prompt.split(". ")[-1]
            source_query_box_label = source_query.split(" ")[1]
            if (
                source_query_box_label in base_box_labels
                and source_query_box_label != base_query_box_label
            ):
                break
            random_choices.remove(random_source_index)

        source_prompts.append(source_prompt)
        base_correct_object = [
            segment.split(" ")[1]
            for segment in base_prompt.split(". ")[0].split(", ")
            if source_query_box_label in segment.split(" ")
        ]
        labels.append(tokenizer.encode(base_correct_object)[1])

    base_input_tokens = tokenizer(base_prompts, padding=True, return_tensors="pt")[
        "input_ids"
    ]
    base_last_token_indices = (
        tokenizer(base_prompts, padding=True, return_tensors="pt")[
            "attention_mask"
        ].sum(dim=1)
        - 1
    )
    source_input_tokens = tokenizer(source_prompts, padding=True, return_tensors="pt")[
        "input_ids"
    ]
    source_last_token_indices = (
        tokenizer(source_prompts, padding=True, return_tensors="pt")[
            "attention_mask"
        ].sum(dim=1)
        - 1
    )
    output_ids = torch.tensor(labels)

    return (
        base_input_tokens,
        base_last_token_indices,
        source_input_tokens,
        source_last_token_indices,
        output_ids,
    )


def object_value_desiderata(
    tokenizer,
    num_samples,
    data_file,
    correct_pred_indices,
    num_boxes,
    object_file,
    alt_format=True,
):
    with open(data_file) as f:
        data = [json.loads(line) for line in f]

    # data = [data[i] for i in correct_pred_indices]

    assert num_samples <= len(data)
    base_prompts, source_prompts, labels = [], [], []

    for i in range(0, num_samples):
        base_prompt = " ".join(data[i]["sentence"].split(" ")[:-1])
        base_query = base_prompt.split(". ")[-1]
        base_query_box_label = base_query.split(" ")[1]
        base_query_box_pos = [
            idx
            for idx, segment in enumerate(base_query.split(". ")[0].split(", "))
            if base_query_box_label in segment
        ][0]
        if base_query_box_pos == -1:
            raise ValueError("Box label not found in the base prompt")
        base_prompts.append(base_prompt)

        source_query_box_pos = base_query_box_pos
        random_choices = list(range(0, num_samples))
        random.shuffle(random_choices)
        while source_query_box_pos == base_query_box_pos:
            random_source_index = random.choice(random_choices)
            source_prompt = " ".join(
                data[random_source_index]["sentence"].split(" ")[:-1]
            )
            source_query = source_prompt.split(". ")[-1]
            source_query_box_label = source_query.split(" ")[1]
            source_query_box_pos = [
                idx
                for idx, segment in enumerate(source_prompt.split(". ")[0].split(", "))
                if source_query_box_label in segment
            ][0]
            random_choices.remove(random_source_index)

        source_prompts.append(source_prompt)

        base_prompt = base_prompt.split(". ")[0]
        correct_object = source_prompt.split(", ")[source_query_box_pos].split(" ")[1]
        labels.append(tokenizer.encode(correct_object)[1])

    base_input_tokens = tokenizer(base_prompts, padding=True, return_tensors="pt")[
        "input_ids"
    ]
    base_last_token_indices = (
        tokenizer(base_prompts, padding=True, return_tensors="pt")[
            "attention_mask"
        ].sum(dim=1)
        - 1
    )
    source_input_tokens = tokenizer(source_prompts, padding=True, return_tensors="pt")[
        "input_ids"
    ]
    source_last_token_indices = (
        tokenizer(source_prompts, padding=True, return_tensors="pt")[
            "attention_mask"
        ].sum(dim=1)
        - 1
    )
    output_ids = torch.tensor(labels)

    return (
        base_input_tokens,
        base_last_token_indices,
        source_input_tokens,
        source_last_token_indices,
        output_ids,
    )


def positional_desiderata(
    tokenizer,
    num_samples,
    data_file,
    correct_pred_indices,
    num_boxes,
    object_file,
    alt_format=True,
):
    with open(data_file) as f:
        data = [json.loads(line) for line in f]

    # data = [data[i] for i in correct_pred_indices]

    assert num_samples <= len(data)
    base_prompts, source_prompts, labels = [], [], []

    for i in range(0, num_samples):
        base_prompt = " ".join(data[i]["sentence"].split(" ")[:-1])
        base_query = base_prompt.split(". ")[-1]
        base_query_box_label = base_query.split(" ")[1]
        base_query_box_pos = [
            idx
            for idx, segment in enumerate(base_query.split(". ")[0].split(", "))
            if base_query_box_label in segment
        ][0]
        if base_query_box_pos == -1:
            raise ValueError("Box label not found in the base prompt")
        base_prompts.append(base_prompt)

        source_query_box_pos = base_query_box_pos
        random_choices = list(range(0, num_samples))
        random.shuffle(random_choices)
        while source_query_box_pos == base_query_box_pos:
            random_source_index = random.choice(random_choices)
            source_prompt = " ".join(
                data[random_source_index]["sentence"].split(" ")[:-1]
            )
            source_query = source_prompt.split(". ")[-1]
            source_query_box_label = source_query.split(" ")[1]
            source_query_box_pos = [
                idx
                for idx, segment in enumerate(source_prompt.split(". ")[0].split(", "))
                if source_query_box_label in segment
            ][0]
            random_choices.remove(random_source_index)

        source_prompts.append(source_prompt)

        base_prompt = base_prompt.split(". ")[0]
        correct_object = base_prompt.split(", ")[source_query_box_pos].split(" ")[1]
        labels.append(tokenizer.encode(correct_object)[1])

    base_input_tokens = tokenizer(base_prompts, padding=True, return_tensors="pt")[
        "input_ids"
    ]
    base_last_token_indices = (
        tokenizer(base_prompts, padding=True, return_tensors="pt")[
            "attention_mask"
        ].sum(dim=1)
        - 1
    )
    source_input_tokens = tokenizer(source_prompts, padding=True, return_tensors="pt")[
        "input_ids"
    ]
    source_last_token_indices = (
        tokenizer(source_prompts, padding=True, return_tensors="pt")[
            "attention_mask"
        ].sum(dim=1)
        - 1
    )
    output_ids = torch.tensor(labels)

    return (
        base_input_tokens,
        base_last_token_indices,
        source_input_tokens,
        source_last_token_indices,
        output_ids,
    )


def correct_object_position_fetcher_desiderata(
    tokenizer,
    num_samples,
    data_file,
    object_file,
    num_boxes,
    alt_format=False,
):
    with open(data_file) as f:
        data = [json.loads(line) for line in f]

    objects = pd.read_csv(object_file)

    assert num_samples <= len(data)
    base_prompts, source_prompts, base_labels = [], [], []

    for i in range(0, num_samples, num_boxes):
        for j in range(num_boxes):
            if i + j >= num_samples:
                break

            random_source_index = random.choice(list(range(0, num_samples, num_boxes)))
            random_source_index += (j) % num_boxes
            source_prompt = " ".join(
                data[random_source_index]["sentence"].split(" ")[:-1]
            )
            source_box_label = source_prompt.split(". ")[-1].split(" ")[1]
            # generate a random english alphabet in upper case
            random_alphabet = chr(random.randint(65, 90))
            # random_box_label = random_alphabet
            # while random_alphabet == random_box_label:
            #     random_box_label = chr(random.randint(65, 90))

            # generate 3 random single digit numbers
            # random_numbers = [random.randint(0, 9) for _ in range(3)]
            # while len(list(set(random_numbers))) != 3:
            #     random_numbers = [random.randint(0, 9) for _ in range(3)]
            # source_prompt = source_prompt.replace(source_box_label, random_alphabet)

            source_segments = source_prompt.split(". ")[0].split(", ")

            if alt_format:
                for segment_idx in range(len(source_segments)):
                    if source_box_label in source_segments[segment_idx].split(" "):
                        source_segments[segment_idx] = (
                            source_segments[segment_idx].split(" ")[0]
                            + " bottle and "
                            + " ".join(source_segments[segment_idx].split(" ")[1:])
                        )
                        source_segments[segment_idx] = source_segments[
                            segment_idx
                        ].replace(" is", " are")
                    correct_object = source_segments[segment_idx].split(" ")[1]
                    # source_segments[segment_idx] = f"the table has Box {source_box_label}"

                    # source_segments[segment_idx] = source_segments[segment_idx].replace(
                    #     " in",
                    #     " on",
                    # )
                    # source_segments[segment_idx] = source_segments[segment_idx].replace(
                    #     "the ", ""
                    # )
                    # source_segments[segment_idx] = source_segments[segment_idx].replace(
                    #     "The ", ""
                    # )
                    # source_segments[segment_idx] += " which is on the table"
                    if segment_idx == 0:
                        source_segments[segment_idx] = (
                            source_segments[segment_idx][0].upper()
                            + source_segments[segment_idx][1:]
                        )

            else:
                pass
                # for segment_idx in range(len(source_segments)):
                #     if source_box_label in source_segments[segment_idx].split(" "):
                #         correct_object = source_segments[segment_idx].split(" ")[-1]
                #         source_segments[
                #             segment_idx
                #         ] = f"the {correct_object} is in Box {source_box_label}"
                #     if segment_idx == 0:
                #         source_segments[segment_idx] = (
                #             source_segments[segment_idx][0].upper()
                #             + source_segments[segment_idx][1:]
                #         )

            source_prompt = (
                ", ".join(source_segments) + ". " + source_prompt.split(". ")[-1]
            )
            # source_prompt = source_prompt.replace(" in", " contained in")
            source_prompts.append(source_prompt)

            base_prompt = " ".join(data[i + j]["sentence"].split(" ")[:-1])
            base_query = base_prompt.split(". ")[-1]
            base_query_box_label = base_query.split(" ")[1]
            base_segments = base_prompt.split(". ")[0].split(", ")

            for seg_idx, segment in enumerate(base_segments):
                if base_query_box_label in segment.split(" "):
                    base_segments[seg_idx] = (
                        base_segments[seg_idx].split(" ")[0]
                        + " apple and "
                        + " ".join(base_segments[seg_idx].split(" ")[1:])
                    )
                    base_segments[seg_idx] = base_segments[seg_idx].replace(
                        " is", " are"
                    )

            base_context = ", ".join(base_segments)
            base_query = base_query.replace(base_query_box_label, random_alphabet)
            base_prompt = base_context + ". " + base_query
            base_prompts.append(base_prompt)
            label = data[i + ((j) % num_boxes)]["sentence"].split(" ")[-1][:-1]
            base_labels.append(tokenizer.encode(label)[1])

    base_input_tokens = tokenizer(base_prompts, padding=True, return_tensors="pt")[
        "input_ids"
    ]
    base_last_token_indices = (
        tokenizer(base_prompts, padding=True, return_tensors="pt")[
            "attention_mask"
        ].sum(dim=1)
        - 1
    )
    source_input_tokens = tokenizer(source_prompts, padding=True, return_tensors="pt")[
        "input_ids"
    ]
    source_last_token_indices = (
        tokenizer(source_prompts, padding=True, return_tensors="pt")[
            "attention_mask"
        ].sum(dim=1)
        - 1
    )
    output_ids = torch.tensor(base_labels)

    return (
        base_input_tokens,
        base_last_token_indices,
        source_input_tokens,
        source_last_token_indices,
        output_ids,
    )


def box_label_value_fetcher_desiderata(
    tokenizer,
    num_samples,
    data_file,
    object_file,
    num_boxes,
    alt_format=False,
):
    with open(data_file) as f:
        data = [json.loads(line) for line in f]

    objects = pd.read_csv(object_file)

    assert num_samples <= len(data)
    base_prompts, source_prompts, base_labels, source_labels = [], [], [], []

    for i in range(0, num_samples, num_boxes):
        for j in range(num_boxes):
            if i + j >= num_samples:
                break
            prompt = " ".join(data[i + j]["sentence"].split(" ")[:-1])
            base_prompts.append(prompt)
            label = data[i + j]["sentence"].split(" ")[-1][:-1]
            base_labels.append(tokenizer.encode(label)[1])

            prompt = " ".join(
                data[i + ((j + 1) % num_boxes)]["sentence"].split(" ")[:-2]
            )
            context = prompt.split(". ")[0]
            query = prompt.split(". ")[-1]
            box_label = query.split(" ")[1]
            context_segs = context.split(", ")

            random_objects = []
            while len(list(set(random_objects))) != 3:
                random_objects = random.sample(objects["object_name"].tolist(), 3)

            for idx in range(len(context_segs)):
                if box_label in context_segs[idx].split(" "):
                    if alt_format:
                        # Remove "the" from the start of the sentence and add " contained"
                        context_segs[idx] = (
                            [random_objects[idx]]
                            + context_segs[idx].split(" ")[2:3]
                            + ["contained"]
                            + context_segs[idx].split(" ")[3:]
                        )
                    else:
                        # Remove "the" located just before the object
                        context_segs[idx] = context_segs[idx].split(" ")[:-2] + [
                            random_objects[idx]
                        ]
                else:
                    if alt_format:
                        context_segs[idx] = (
                            context_segs[idx].split(" ")[:1]
                            + [random_objects[idx]]
                            + context_segs[idx].split(" ")[2:]
                        )
                    else:
                        context_segs[idx] = context_segs[idx].split(" ")[:-1] + [
                            random_objects[idx]
                        ]

                context_segs[idx] = " ".join(context_segs[idx])

            context = ", ".join(context_segs)
            prompt = context + ". The " + query

            source_prompts.append(prompt)
            label = data[i + ((j + 1) % num_boxes)]["sentence"].split(" ")[-1][:-1]
            source_labels.append(tokenizer.encode(label)[1])

    base_input_tokens = tokenizer(base_prompts, padding=True, return_tensors="pt")[
        "input_ids"
    ]
    base_last_token_indices = (
        tokenizer(base_prompts, padding=True, return_tensors="pt")[
            "attention_mask"
        ].sum(dim=1)
        - 1
    )
    source_input_tokens = tokenizer(source_prompts, padding=True, return_tensors="pt")[
        "input_ids"
    ]
    source_last_token_indices = (
        tokenizer(source_prompts, padding=True, return_tensors="pt")[
            "attention_mask"
        ].sum(dim=1)
        - 1
    )
    output_ids = torch.tensor(source_labels)

    return (
        base_input_tokens,
        base_last_token_indices,
        source_input_tokens,
        source_last_token_indices,
        output_ids,
    )


def correct_obj_value_fetcher_desiderata_2(
    tokenizer,
    num_samples,
    data_file,
    num_boxes,
    object_file,
    alt_format=False,
):
    with open(data_file) as f:
        data = [json.loads(line) for line in f]

    objects = pd.read_csv(object_file)

    assert num_samples <= len(data)
    base_prompts, source_prompts, source_labels = [], [], []

    for i in range(0, num_samples, num_boxes):
        for j in range(num_boxes):
            if i + j >= num_samples:
                break
            prompt = " ".join(data[i + j]["sentence"].split(" ")[:-1])
            base_prompts.append(prompt)
            label = data[i + j]["sentence"].split(" ")[-1][:-1]

            random_object = random.choice(objects["object_name"].tolist())

            box_label = prompt.split(". ")[-1].split(" ")[1]
            context_segments = prompt.split(". ")[0].split(", ")
            for idx in range(len(context_segments)):
                if box_label in context_segments[idx].split(" "):
                    context_segments[idx] = context_segments[idx].replace(
                        label, random_object
                    )

            context = ", ".join(context_segments)
            prompt = context + ". " + prompt.split(". ")[-1]
            source_prompts.append(prompt)
            source_labels.append(tokenizer.encode(random_object)[1])

    base_input_tokens = tokenizer(base_prompts, padding=True, return_tensors="pt")[
        "input_ids"
    ]
    base_last_token_indices = (
        tokenizer(base_prompts, padding=True, return_tensors="pt")[
            "attention_mask"
        ].sum(dim=1)
        - 1
    )
    source_input_tokens = tokenizer(source_prompts, padding=True, return_tensors="pt")[
        "input_ids"
    ]
    source_last_token_indices = (
        tokenizer(source_prompts, padding=True, return_tensors="pt")[
            "attention_mask"
        ].sum(dim=1)
        - 1
    )
    output_ids = torch.tensor(source_labels)

    return (
        base_input_tokens,
        base_last_token_indices,
        source_input_tokens,
        source_last_token_indices,
        output_ids,
    )


def correct_obj_value_fetcher_desiderata_1(
    tokenizer,
    num_samples,
    data_file,
    num_boxes,
    object_file,
    alt_format=False,
):
    with open(data_file) as f:
        data = [json.loads(line) for line in f]

    objects = pd.read_csv(object_file)

    assert num_samples <= len(data)
    base_prompts, source_prompts, source_labels = [], [], []

    for i in range(0, num_samples, num_boxes):
        for j in range(num_boxes):
            if i + j >= num_samples:
                break
            prompt = " ".join(data[i + j]["sentence"].split(" ")[:-1])
            base_prompts.append(prompt)
            label = data[i + j]["sentence"].split(" ")[-1][:-1]

            random_object = random.choice(objects["object_name"].tolist())

            random_data_index = random.choice(list(range(0, num_samples, num_boxes)))
            random_data_index += (j + 1) % num_boxes
            prompt = " ".join(data[random_data_index]["sentence"].split(" ")[:-1])
            if alt_format:
                prompt = prompt.replace(" in", " contained in")
            else:
                prompt = prompt.replace(" the", "")

            # context = prompt.split(". ")[0]
            # query = prompt.split(". ")[-1]
            # box_label = query.split(" ")[1]
            # context_segs = context.split(",")
            # for idx in range(len(context_segs)):
            #     if box_label in context_segs[idx].split(" "):
            #         context_segs[idx] = context_segs[idx].replace(" the", "")
            #         if alt_format:
            #             context_segs[idx] = context_segs[idx].replace(" in", " contained in")
            # context = ",".join(context_segs)
            # prompt = context + ". " + query

            source_prompts.append(prompt)
            label = data[random_data_index]["sentence"].split(" ")[-1][:-1]
            source_labels.append(tokenizer.encode(label)[1])

    base_input_tokens = tokenizer(base_prompts, padding=True, return_tensors="pt")[
        "input_ids"
    ]
    base_last_token_indices = (
        tokenizer(base_prompts, padding=True, return_tensors="pt")[
            "attention_mask"
        ].sum(dim=1)
        - 1
    )
    source_input_tokens = tokenizer(source_prompts, padding=True, return_tensors="pt")[
        "input_ids"
    ]
    source_last_token_indices = (
        tokenizer(source_prompts, padding=True, return_tensors="pt")[
            "attention_mask"
        ].sum(dim=1)
        - 1
    )
    output_ids = torch.tensor(source_labels)

    return (
        base_input_tokens,
        base_last_token_indices,
        source_input_tokens,
        source_last_token_indices,
        output_ids,
    )


def object_alignment_example_sampler(
    tokenizer,
    num_samples,
    data_file,
    architecture,
    object_file,
    num_ents_or_ops,
    few_shot,
    alt_examples,
):
    num_samples = 2 * num_samples
    (
        input_ids,
        last_token_indices,
        output_ids,
        object_ids,
    ) = object_alignment_example_generator(
        tokenizer, num_samples, data_file, object_file, few_shot, alt_examples
    )

    all_base_input_ids = []
    all_base_input_last_pos = []
    all_source_input_ids = []
    all_source_input_last_pos = []
    all_ctf_output_ids = []
    all_object_ids = []
    all_intervention_ids = []

    for i in range(0, num_samples, 2):
        all_base_input_ids += [input_ids[i]]
        all_source_input_ids += [input_ids[i + 1]]
        all_base_input_last_pos += [last_token_indices[i]]
        all_source_input_last_pos += [last_token_indices[i + 1]]
        all_ctf_output_ids += [output_ids[i + 1]]
        all_object_ids += [object_ids[i]]
        all_intervention_ids += [0]

    return (
        all_base_input_ids,
        all_base_input_last_pos,
        all_source_input_ids,
        all_source_input_last_pos,
        all_ctf_output_ids,
        all_object_ids,
        all_intervention_ids,
    )


def get_samples_with_correct_prediction(
    model,
    tokenizer,
    num_samples,
    data_file,
):
    with open(data_file) as f:
        dataset = [json.loads(line) for line in f]

    assert num_samples <= len(dataset)
    prompts, labels = [], []

    for data in dataset:
        prompt = " ".join(data["sentence"].split(" ")[:-1])
        label = data["sentence"].split(" ")[-1][:-1]
        input_ids = tokenizer(prompt, return_tensors="pt")["input_ids"].to(model.device)
        logits = model(input_ids).logits
        predictions = torch.argmax(logits[0, -1, :], dim=-1)
        if predictions == tokenizer.encode(label)[1]:
            prompts.append(prompt)
            labels.append(tokenizer.encode(label)[1])

        if len(prompts) >= num_samples:
            break

        del input_ids, logits, predictions
        torch.cuda.empty_cache()

    input_tokens = tokenizer(prompts, padding=True, return_tensors="pt")
    last_token_indices = input_tokens["attention_mask"].sum(dim=1) - 1
    output_ids = torch.tensor(labels)

    input_ids = input_tokens["input_ids"]
    last_token_indices = last_token_indices

    return input_ids, last_token_indices, output_ids


def entity_tracking_example_sampler(tokenizer, num_samples, data_file, architecture):
    with open(data_file) as f:
        data = [json.loads(line) for line in f]

    assert num_samples <= len(data)
    prompts, labels = [], []

    for i in range(num_samples):
        label = data[i]["sentence"].split(" ")[-1][:-1]
        prompt = " ".join(data[i]["sentence"].split(" ")[:-1])
        prompts.append(prompt)

        # 0th index will be BOS token for llama-like tokenizer
        if architecture in [
            "AlignableLlamaForCausalLM",
            "LLaMAForCausalLM",
            "LlamaForCausalLM",
            "LlaMAForCausalLM",
        ]:
            labels.append(tokenizer.encode(label)[1])
        elif architecture == "GPT2LMHeadModel":
            labels.append(tokenizer.encode(label)[0])
        else:
            raise ValueError(f"Unknown architecture {architecture}")

    input_tokens = tokenizer(prompts, padding=True, return_tensors="pt")
    last_token_indices = input_tokens["attention_mask"].sum(dim=1) - 1
    output_ids = torch.tensor(labels)
    input_ids = input_tokens["input_ids"]

    return input_ids, last_token_indices, output_ids


def random_label_samples_for_path_patching(
    tokenizer,
    num_samples,
    data_file,
    num_ents_or_ops,
    architecture,
    few_shot,
    alt_examples,
):
    input_ids, last_token_indices, output_ids = entity_tracking_example_sampler(
        tokenizer, num_samples, data_file, architecture, few_shot, alt_examples
    )

    all_base_input_ids = []
    all_base_input_last_pos = []
    all_source_input_ids = []
    all_source_input_last_pos = []
    all_ctf_output_ids = []

    for i in range(0, num_samples, num_ents_or_ops):
        for j in range(num_ents_or_ops):
            if i + j >= num_samples:
                break

            all_base_input_ids += [input_ids[i + j]]
            all_base_input_last_pos += [last_token_indices[i + j]]
            all_ctf_output_ids += [output_ids[i + j]]

            random_source_index = random.choice(
                list(range(0, num_samples, num_ents_or_ops))
            )
            random_source_index += (j + 1) % num_ents_or_ops
            all_source_input_ids += [input_ids[random_source_index]]
            all_source_input_last_pos += [last_token_indices[random_source_index]]

    return (
        all_base_input_ids,
        all_base_input_last_pos,
        all_source_input_ids,
        all_source_input_last_pos,
        all_ctf_output_ids,
    )


def different_format_samples(
    tokenizer,
    num_samples,
    data_file_1,
    data_file_2,
    architecture,
    few_shot,
    alt_examples,
):
    (
        clean_input_ids,
        clean_last_token_indices,
        clean_output_ids,
    ) = entity_tracking_example_sampler(
        tokenizer, num_samples, data_file_1, architecture, few_shot, alt_examples
    )

    (
        corrupt_input_ids,
        corrupt_last_token_indices,
        corrupt_output_ids,
    ) = entity_tracking_example_sampler(
        tokenizer, num_samples, data_file_2, architecture, few_shot, alt_examples
    )

    all_base_input_ids = []
    all_base_input_last_pos = []
    all_source_input_ids = []
    all_source_input_last_pos = []
    all_ctf_output_ids = []

    for i in range(num_samples):
        all_base_input_ids += [clean_input_ids[i]]
        all_base_input_last_pos += [clean_last_token_indices[i]]
        all_source_input_ids += [corrupt_input_ids[(i + 1) % num_samples]]
        all_source_input_last_pos += [corrupt_last_token_indices[(i + 1) % num_samples]]
        all_ctf_output_ids += [clean_output_ids[i]]

    return (
        all_base_input_ids,
        all_base_input_last_pos,
        all_source_input_ids,
        all_source_input_last_pos,
        all_ctf_output_ids,
    )


def random_samples(
    tokenizer, num_samples, data_file, architecture, few_shot, alt_examples
):
    with open(data_file) as f:
        data = [json.loads(line) for line in f]

    assert num_samples <= len(data)
    prompts, incorrect_object_tokens, labels = [], [], []

    existing_indices = []
    for _ in range(num_samples):
        i = random.randint(0, len(data))
        while i in existing_indices:
            i = random.randint(0, len(data))
        existing_indices.append(i)

        label = data[i]["sentence"].split(" ")[-1][:-1]
        prompt = " ".join(data[i]["sentence"].split(" ")[:-1])
        prompts.append(prompt)

        # 0th index will be BOS token for llama-like tokenizer
        if architecture in [
            "AlignableLlamaForCausalLM",
            "LLaMAForCausalLM",
            "LlamaForCausalLM",
            "LlaMAForCausalLM",
        ]:
            labels.append(tokenizer.encode(label)[1])
        elif architecture == "GPT2LMHeadModel":
            labels.append(tokenizer.encode(label)[0])
        else:
            raise ValueError(f"Unknown architecture {architecture}")

    input_tokens = tokenizer(prompts, padding=True, return_tensors="pt")
    last_token_indices = input_tokens["attention_mask"].sum(dim=1) - 1
    output_ids = torch.tensor(labels)

    input_ids = input_tokens["input_ids"]
    last_token_indices = last_token_indices
    output_ids = output_ids

    return input_ids, last_token_indices, output_ids


def box_index_aligner_examples(
    model,
    tokenizer,
    num_samples,
    data_file,
    num_ents_or_ops,
    architecture,
):
    (
        input_ids,
        last_token_indices,
        output_ids,
    ) = entity_tracking_example_sampler(tokenizer, num_samples, data_file, architecture)

    all_base_input_ids = []
    all_base_input_last_pos = []
    all_source_input_ids = []
    all_source_input_last_pos = []
    all_ctf_output_ids = []
    all_intervention_ids = []
    all_incorrect_output_ids = []

    for i in range(0, num_samples, num_ents_or_ops):
        for j in range(num_ents_or_ops):
            if i + j >= num_samples:
                break

            all_base_input_ids += [input_ids[i + j]]
            all_base_input_last_pos += [last_token_indices[i + j]]
            all_ctf_output_ids += [output_ids[i + j]]

            random_source_index = random.choice(
                list(
                    range(0, num_samples - ((j + 1) % num_ents_or_ops), num_ents_or_ops)
                )
            )
            random_source_index += (j + 1) % num_ents_or_ops
            source_example = input_ids[random_source_index].clone()

            # Change the query box label with a random alphabet
            random_alphabet = chr(random.randint(65, 90))
            random_alphabet_token = tokenizer(
                random_alphabet, return_tensors="pt"
            ).input_ids[0, 1]
            source_example[-3] = random_alphabet_token

            all_source_input_ids += [source_example]
            all_source_input_last_pos += [last_token_indices[random_source_index]]

            all_intervention_ids += [0]

    return (
        all_base_input_ids,
        all_base_input_last_pos,
        all_source_input_ids,
        all_source_input_last_pos,
        all_ctf_output_ids,
        all_intervention_ids,
        all_incorrect_output_ids,
    )


def modified_box_name_alignment_example_sampler(
    tokenizer,
    num_samples,
    data_file,
    object_file,
    num_ents_or_ops,
    architecture,
    few_shot,
    alt_examples,
):
    (
        input_ids,
        last_token_indices,
        output_ids,
        incorrect_object_ids,
    ) = entity_tracking_example_sampler(
        tokenizer, num_samples, data_file, architecture, few_shot, alt_examples
    )

    all_base_input_ids = []
    all_base_input_last_pos = []
    all_source_input_ids = []
    all_source_input_last_pos = []
    all_ctf_output_ids = []
    all_exp_objects = []
    all_intervention_ids = []

    for i in range(0, num_samples, num_ents_or_ops):
        if i + num_ents_or_ops > num_samples:
            break
        for j in range(num_ents_or_ops):
            all_base_input_ids += [input_ids[i + j]]
            all_base_input_last_pos += [last_token_indices[i + j]]
            all_exp_objects += [incorrect_object_ids[i + j]]

            random_source_index = random.choice(
                range(0, num_samples, num_ents_or_ops)
            ) + ((j + 1) % num_ents_or_ops)
            all_source_input_ids += [input_ids[random_source_index]]
            all_source_input_last_pos += [last_token_indices[random_source_index]]

            all_ctf_output_ids += [output_ids[i + (j + 1) % num_ents_or_ops]]
            all_intervention_ids += [0]

    return (
        all_base_input_ids,
        all_base_input_last_pos,
        all_source_input_ids,
        all_source_input_last_pos,
        all_ctf_output_ids,
        all_exp_objects,
        all_intervention_ids,
    )


def box_name_alignment_example_sampler(
    tokenizer, num_samples, data_file, architecture, object_file, num_ents_or_ops
):
    input_ids, last_token_indices, output_ids = entity_tracking_example_sampler(
        tokenizer, num_samples, data_file, architecture
    )

    all_base_input_ids = []
    all_base_input_last_pos = []
    all_source_input_ids = []
    all_source_input_last_pos = []
    all_ctf_output_ids = []
    all_intervention_ids = []

    for i in range(0, num_samples, num_ents_or_ops):
        if i + num_ents_or_ops > num_samples:
            break
        for j in range(num_ents_or_ops):
            all_base_input_ids += [input_ids[i]]
            all_source_input_ids += [input_ids[i + j]]
            all_base_input_last_pos += [last_token_indices[i]]
            all_source_input_last_pos += [last_token_indices[i + j]]

            all_ctf_output_ids += [output_ids[i + j]]
            all_intervention_ids += [0]

    return (
        all_base_input_ids,
        all_base_input_last_pos,
        all_source_input_ids,
        all_source_input_last_pos,
        all_ctf_output_ids,
        all_intervention_ids,
    )


def alignment_example_sampler(
    tokenizer,
    data_size,
    aligner_func,
    data_file,
    num_ents_or_ops=None,
    object_file=None,
    architecture=None,
    few_shot=False,
    alt_examples=False,
):
    (
        all_base_input_ids,
        all_base_input_last_pos,
        all_source_input_ids,
        all_source_input_last_pos,
        all_ctf_output_ids,
        all_incorrect_object_ids,
        all_intervention_ids,
    ) = aligner_func(
        tokenizer=tokenizer,
        num_samples=data_size,
        data_file=data_file,
        object_file=object_file,
        num_ents_or_ops=num_ents_or_ops,
        architecture=architecture,
        few_shot=few_shot,
        alt_examples=alt_examples,
    )

    return (
        all_base_input_ids,
        all_base_input_last_pos,
        all_source_input_ids,
        all_source_input_last_pos,
        all_ctf_output_ids,
        all_incorrect_object_ids,
        all_intervention_ids,
    )