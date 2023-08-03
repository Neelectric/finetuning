import math
import torch
from einops import einsum
from baukit import TraceDict


def apply_causal_mask(attn_scores):
    ignore = torch.tensor(torch.finfo(attn_scores.dtype).min)
    mask = torch.triu(
        torch.ones(attn_scores.size(-2), attn_scores.size(-1), device=attn_scores.device),
        diagonal=1,
    ).bool()
    attn_scores.masked_fill_(mask, ignore)
    return attn_scores


def rotate_half(x):
    """Rotates half the hidden dims of the input."""
    x1 = x[..., : x.shape[-1] // 2]
    x2 = x[..., x.shape[-1] // 2 :]
    return torch.cat((-x2, x1), dim=-1)


def apply_rotary_pos_emb(q, k, cos, sin, position_ids):
    # The first two dimensions of cos and sin are always 1, so we can `squeeze` them.
    cos = cos.squeeze(1).squeeze(0)  # [seq_len, dim]
    sin = sin.squeeze(1).squeeze(0)  # [seq_len, dim]
    cos = cos[position_ids].unsqueeze(1)  # [bs, 1, seq_len, dim]
    sin = sin[position_ids].unsqueeze(1)  # [bs, 1, seq_len, dim]
    q_embed = (q * cos) + (rotate_half(q) * sin)
    k_embed = (k * cos) + (rotate_half(k) * sin)
    return q_embed, k_embed


def get_attn_scores(model, tokens, layer):
    modules = [
        [
            f"model.layers.{i}.self_attn.k_proj",
            f"model.layers.{i}.self_attn.q_proj",
            f"model.layers.{i}.self_attn.v_proj",
        ]
        for i in range(model.config.num_hidden_layers)
    ]
    modules = [item for sublist in modules for item in sublist]

    with torch.no_grad():
        with TraceDict(model, modules) as residual:
            model(tokens)

        batch_size, seq_len = tokens.shape
        n_heads = model.config.num_attention_heads
        d_head = model.config.hidden_size // n_heads

        key = (
            residual[f"model.layers.{layer}.self_attn.k_proj"]
            .output.view(batch_size, seq_len, n_heads, d_head)
            .transpose(1, 2)
        )
        query = (
            residual[f"model.layers.{layer}.self_attn.q_proj"]
            .output.view(batch_size, seq_len, n_heads, d_head)
            .transpose(1, 2)
        )
        value = (
            residual[f"model.layers.{layer}.self_attn.v_proj"]
            .output.view(batch_size, seq_len, n_heads, d_head)
            .transpose(1, 2)
        )

        kv_seq_len = key.shape[-2]
        cos, sin = model.model.layers[layer].self_attn.rotary_emb(value, seq_len=kv_seq_len)
        positions = [i for i in range(seq_len)]
        positions = torch.tensor(positions).unsqueeze(0).repeat(batch_size, 1).to("cuda")
        query, key = apply_rotary_pos_emb(query, key, cos, sin, positions)

        attn_scores = einsum(
            key,
            query,
            "batch n_heads key_pos d_head, batch n_heads query_pos d_head -> batch n_heads query_pos key_pos",
        )
        attn_scores = attn_scores / math.sqrt(d_head)
        attn_scores = apply_causal_mask(attn_scores)
        attn_scores = torch.softmax(attn_scores, dim=-1)

    return attn_scores


def perf_metric(
    patched_logits, answer, base_logits, source_logits, base_last_token_pos, source_last_token_pos
):
    """Computes the impact of patching on the model's output logits on a scale of [0, 1]."""
    # TODO: Remove for loop
    score = 0
    patched = torch.log_softmax(
        patched_logits[0, base_last_token_pos],
        dim=-1,
    )
    corrupt = torch.log_softmax(
        source_logits[0, source_last_token_pos],
        dim=-1,
    )
    clean = torch.log_softmax(base_logits[0, -1], dim=-1)
    print(patched.shape, corrupt.shape, clean.shape)
    numerator = patched[answer] - corrupt[answer]
    denominator = clean[answer] - corrupt[answer]
    score += numerator / denominator

    return score / batch_size


def compute_topk_components(patching_scores: torch.Tensor, k: int, largest=True):
    """Computes the topk most influential components (i.e. heads) for patching."""
    top_indices = torch.topk(patching_scores.flatten(), k, largest=largest).indices

    # Convert the top_indices to 2D indices
    row_indices = top_indices // patching_scores.shape[1]
    col_indices = top_indices % patching_scores.shape[1]
    top_components = torch.stack((row_indices, col_indices), dim=1)
    # Get the top indices as a list of 2D indices (row, column)
    top_components = top_components.tolist()
    return top_components