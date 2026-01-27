"""
Embedding Text Generator for Stage 4.

Converts canonical entities from Stage 3 into rich, descriptive text
suitable for generating embeddings. The generated text captures all
important aspects of an entity including location, attributes, consensus
data, ratings, costs, and themes.

Usage:
    from src.processors.embedding_generator import generate_entity_embedding_text

    embedding_text = generate_entity_embedding_text(canonical_entity)
    print(f"Generated {len(embedding_text.split())} words")
"""

from typing import List, Tuple, Optional, Dict, Any
from loguru import logger


def generate_entity_embedding_text(canonical_entity: dict) -> str:
    """
    Generate rich descriptive text for embedding from canonical entity.

    Combines all relevant entity information into natural language text
    optimized for semantic search:
    - Entity identity (name, type, location)
    - Attributes and characteristics
    - Consensus metrics (ratings, mentions, themes)
    - Profile-specific recommendations
    - Cost information
    - Common experiences and tips
    - **NEW: WHEN TO VISIT** - Temporal information (seasons, times, duration)
    - **NEW: HOW TO GET THERE** - Logistics (transport, booking, accessibility)
    - **NEW: PRACTICAL TIPS** - Practical details (fees, dress code, hours)

    Args:
        canonical_entity: Canonical entity dict from Stage 3

    Returns:
        Rich descriptive text (400-600 words typical, enhanced from ~200 words)

    Example:
        >>> entity = load_canonical_entity("attraction_bangkok_001")
        >>> text = generate_entity_embedding_text(entity)
        >>> len(text.split())
        487
    """
    parts = []

    # 1. Entity identity - name, type, location
    name = canonical_entity.get('canonical_name', 'Unknown')
    entity_type = canonical_entity.get('entity_type', 'unknown')
    location = canonical_entity.get('location', 'Unknown')

    # Build location string
    location_str = location
    if location and location != 'Unknown':
        parts.append(f"{name} is a {entity_type} located in {location}.")
    else:
        parts.append(f"{name} is a {entity_type}.")

    # Add aliases if available
    aliases = canonical_entity.get('aliases', [])
    if aliases and len(aliases) > 1:
        # Filter out the canonical name from aliases
        other_names = [a for a in aliases if a.lower() != name.lower()][:3]
        if other_names:
            parts.append(f"Also known as: {', '.join(other_names)}.")

    # 2. Extract consensus data
    consensus = canonical_entity.get('consensus', {})
    mention_count = consensus.get('mention_count', 0)
    avg_rating = consensus.get('avg_rating')
    themes = consensus.get('themes', [])
    sentiment_dist = consensus.get('sentiment_distribution', {})

    # 3. Overall summary with ratings
    if mention_count > 0:
        mention_str = f"mentioned {mention_count} time{'s' if mention_count != 1 else ''} across different travel videos"

        if avg_rating is not None:
            rating_emoji = "⭐" * int(round(avg_rating))
            parts.append(f"This {entity_type} has been {mention_str} with an average rating of {avg_rating}/5.0 {rating_emoji}.")
        else:
            parts.append(f"This {entity_type} has been {mention_str}.")

    # 4. Sentiment distribution
    positive_count = sentiment_dist.get('positive', 0)
    negative_count = sentiment_dist.get('negative', 0)
    neutral_count = sentiment_dist.get('neutral', 0)

    if positive_count + negative_count + neutral_count > 0:
        sentiment_parts = []
        if positive_count > 0:
            sentiment_parts.append(f"{positive_count} positive")
        if neutral_count > 0:
            sentiment_parts.append(f"{neutral_count} neutral")
        if negative_count > 0:
            sentiment_parts.append(f"{negative_count} negative")

        if sentiment_parts:
            parts.append(f"Traveler sentiment: {', '.join(sentiment_parts)} reviews.")

    # 5. Common themes and characteristics
    if themes:
        # Take top 10 themes
        top_themes = themes[:10]
        parts.append(f"Common themes and characteristics: {', '.join(top_themes)}.")

    # 6. Cost information
    cost_info = consensus.get('cost_info', {})
    overall_cost = cost_info.get('overall', {})

    if overall_cost:
        min_cost = overall_cost.get('min')
        max_cost = overall_cost.get('max')
        avg_cost = overall_cost.get('avg')
        currency = overall_cost.get('currency', 'THB')

        if avg_cost is not None:
            parts.append(f"Average cost: {avg_cost:.0f} {currency}.")
        elif min_cost is not None and max_cost is not None:
            parts.append(f"Cost range: {min_cost:.0f}-{max_cost:.0f} {currency}.")
        elif min_cost is not None:
            parts.append(f"Starting from {min_cost:.0f} {currency}.")

    # 7. Profile-specific recommendations
    best_for = consensus.get('best_for', [])
    not_recommended_for = consensus.get('not_recommended_for', [])

    if best_for:
        parts.append(f"Best suited for: {', '.join(best_for)} travelers.")

    if not_recommended_for:
        parts.append(f"May not be ideal for: {', '.join(not_recommended_for)}.")

    # 8. Profile-specific metrics (detailed breakdown)
    profile_metrics = consensus.get('profile_metrics', {})

    if profile_metrics:
        profile_summaries = []

        # Sort by mention count to prioritize most-mentioned profiles
        sorted_profiles = sorted(
            profile_metrics.items(),
            key=lambda x: x[1].get('mention_count', 0),
            reverse=True
        )[:3]  # Top 3 profiles

        for profile_key, metrics in sorted_profiles:
            profile_rating = metrics.get('avg_rating')
            profile_mentions = metrics.get('mention_count', 0)
            profile_themes = metrics.get('common_themes', [])[:5]

            # Parse profile key (e.g., "couple_26-35_mid-range")
            profile_parts = profile_key.split('_')
            traveler_type = profile_parts[0] if len(profile_parts) > 0 else 'unknown'

            if profile_rating and profile_mentions > 0:
                profile_desc = f"{traveler_type} travelers"
                if profile_rating >= 4.0:
                    profile_desc += f" highly rate this (⭐{profile_rating:.1f}/5.0)"
                elif profile_rating >= 3.0:
                    profile_desc += f" moderately rate this ({profile_rating:.1f}/5.0)"
                else:
                    profile_desc += f" give mixed reviews ({profile_rating:.1f}/5.0)"

                if profile_themes:
                    profile_desc += f", noting: {', '.join(profile_themes)}"

                profile_summaries.append(profile_desc)

        if profile_summaries:
            parts.append("Traveler experiences: " + "; ".join(profile_summaries) + ".")

    # 9. Extract representative experiences
    experiences = canonical_entity.get('experiences', [])

    if experiences:
        # Sample 1-2 representative experiences
        sample_size = min(2, len(experiences))
        sample_experiences = experiences[:sample_size]

        experience_texts = []
        for exp in sample_experiences:
            exp_text = exp.get('experience', '')
            if exp_text:
                # Truncate long experiences
                if len(exp_text) > 200:
                    exp_text = exp_text[:197] + "..."
                experience_texts.append(exp_text)

        if experience_texts:
            parts.append(f"Traveler experiences include: {' '.join(experience_texts)}")

    # 10. Additional attributes
    attributes = canonical_entity.get('attributes', {})

    if attributes:
        attr_list = []

        # Extract specific useful attributes
        keywords = attributes.get('keywords', [])
        if keywords:
            attr_list.append(f"Keywords: {', '.join(keywords[:10])}")

        travel_style = attributes.get('travel_style', [])
        if travel_style:
            attr_list.append(f"Travel styles: {', '.join(travel_style[:5])}")

        season = attributes.get('season_mentioned', [])
        if season:
            attr_list.append(f"Best seasons: {', '.join(season)}")

        if attr_list:
            parts.append(f"Additional details: {'. '.join(attr_list)}.")

    # 11. WHEN TO VISIT - Temporal Information (NEW!)
    temporal_info = canonical_entity.get('temporal_info', {})
    if temporal_info:
        temporal_parts = []

        # Best seasons
        best_seasons = temporal_info.get('best_seasons', [])
        if best_seasons and isinstance(best_seasons, list) and best_seasons[0] != 'unknown':
            seasons_str = ', '.join(best_seasons[:4])
            temporal_parts.append(f"Best visited during {seasons_str}")

        # Best times of day
        best_times = temporal_info.get('best_times_of_day', [])
        if best_times and isinstance(best_times, list) and best_times[0] != 'unknown':
            times_str = ', '.join(best_times[:3])
            temporal_parts.append(f"ideal times are {times_str}")

        # Typical duration
        typical_duration = temporal_info.get('typical_duration', '')
        if typical_duration and typical_duration != 'unknown':
            temporal_parts.append(f"plan for about {typical_duration}")

        if temporal_parts:
            parts.append(f"WHEN TO VISIT: {', '.join(temporal_parts)}.")

    # 12. HOW TO GET THERE - Logistics Information (NEW!)
    logistics_info = canonical_entity.get('logistics_info', {})
    if logistics_info:
        logistics_parts = []

        # Transport options
        transport_options = logistics_info.get('transport_options', [])
        if transport_options and isinstance(transport_options, list):
            # Filter out 'unknown'
            valid_transport = [t for t in transport_options if t != 'unknown'][:4]
            if valid_transport:
                transport_str = ', '.join(valid_transport)
                logistics_parts.append(f"accessible by {transport_str}")

        # Booking required
        booking_required = logistics_info.get('booking_required', '')
        if booking_required and booking_required != 'unknown':
            if booking_required.lower() in ['yes', 'required', 'recommended']:
                logistics_parts.append("advance booking recommended")
            elif booking_required.lower() in ['no', 'not required', 'walk-in']:
                logistics_parts.append("walk-in friendly")

        # Accessibility
        accessibility = logistics_info.get('accessibility', '')
        if accessibility and accessibility != 'unknown':
            if 'wheelchair' in accessibility.lower() and 'accessible' in accessibility.lower():
                logistics_parts.append("wheelchair accessible")

        if logistics_parts:
            parts.append(f"HOW TO GET THERE: {', '.join(logistics_parts)}.")

    # 13. PRACTICAL TIPS - Practical Information (NEW!)
    practical_tips = canonical_entity.get('practical_tips', {})
    if practical_tips:
        practical_parts = []

        # Entrance fee
        entrance_fee = practical_tips.get('entrance_fee', '')
        if entrance_fee and entrance_fee != 'unknown':
            if entrance_fee.lower() == 'free':
                practical_parts.append("free admission")
            else:
                practical_parts.append(f"entrance fee: {entrance_fee}")

        # Dress code
        dress_code = practical_tips.get('dress_code', '')
        if dress_code and dress_code != 'unknown':
            practical_parts.append(f"dress code: {dress_code}")

        # Opening hours
        opening_hours = practical_tips.get('opening_hours', '')
        if opening_hours and opening_hours != 'unknown':
            practical_parts.append(f"hours: {opening_hours}")

        if practical_parts:
            parts.append(f"PRACTICAL TIPS: {', '.join(practical_parts)}.")

    # 14. Coordinates for context
    coordinates = canonical_entity.get('coordinates', {})
    if coordinates:
        lat = coordinates.get('lat')
        lon = coordinates.get('lon')
        display_name = coordinates.get('display_name')

        if display_name:
            parts.append(f"Full address: {display_name}.")

    # Combine all parts
    embedding_text = " ".join(parts)

    return embedding_text


def validate_embedding_text(text: str, entity_id: str = "unknown") -> bool:
    """
    Validate that embedding text meets quality requirements.

    Checks:
    - Not too short (<50 words)
    - Not too long (>1000 words)
    - Contains key information
    - No placeholder text

    Args:
        text: Generated embedding text
        entity_id: Entity ID for logging

    Returns:
        True if valid, False otherwise
    """
    if not text or not text.strip():
        logger.warning(f"Entity {entity_id}: Empty embedding text")
        return False

    # Word count check
    words = text.split()
    word_count = len(words)

    if word_count < 50:
        logger.warning(f"Entity {entity_id}: Text too short ({word_count} words)")
        return False

    if word_count > 1000:
        logger.warning(f"Entity {entity_id}: Text too long ({word_count} words)")
        return False

    # Check for placeholder text
    placeholders = ['unknown', 'n/a', 'not available', 'todo', 'fixme']
    text_lower = text.lower()

    placeholder_count = sum(1 for p in placeholders if p in text_lower)
    if placeholder_count > 3:
        logger.warning(f"Entity {entity_id}: Too many placeholder values")
        return False

    # Check for key information
    required_keywords = ['is a', 'located', 'travelers', 'rating', 'mentioned']
    found_keywords = sum(1 for kw in required_keywords if kw.lower() in text_lower)

    if found_keywords < 2:
        logger.warning(f"Entity {entity_id}: Missing key information (found {found_keywords}/{len(required_keywords)})")
        return False

    logger.debug(f"Entity {entity_id}: Valid embedding text ({word_count} words)")
    return True


def batch_generate_entity_texts(
    entities: List[Dict[str, Any]],
    show_progress: bool = True
) -> List[Tuple[str, str]]:
    """
    Generate embedding texts for a batch of entities.

    Args:
        entities: List of canonical entity dicts
        show_progress: Whether to show progress logging

    Returns:
        List of (entity_id, embedding_text) tuples

    Example:
        >>> entities = load_all_canonical_entities()
        >>> texts = batch_generate_entity_texts(entities)
        >>> len(texts)
        1536
    """
    results = []
    total = len(entities)
    valid_count = 0
    invalid_count = 0

    logger.info(f"Generating embedding texts for {total} entities...")

    for idx, entity in enumerate(entities, 1):
        entity_id = entity.get('entity_id', f'unknown_{idx}')

        try:
            # Generate text
            embedding_text = generate_entity_embedding_text(entity)

            # Validate
            if validate_embedding_text(embedding_text, entity_id):
                results.append((entity_id, embedding_text))
                valid_count += 1
            else:
                invalid_count += 1
                logger.warning(f"Skipping entity {entity_id} due to validation failure")

            # Progress logging
            if show_progress and idx % 100 == 0:
                logger.info(f"Progress: {idx}/{total} entities processed ({valid_count} valid, {invalid_count} invalid)")

        except Exception as e:
            logger.error(f"Failed to generate text for entity {entity_id}: {e}")
            invalid_count += 1

    logger.info(f"✅ Generated {valid_count} valid embedding texts ({invalid_count} invalid/failed)")

    return results


def get_embedding_text_stats(texts: List[Tuple[str, str]]) -> Dict[str, Any]:
    """
    Calculate statistics about generated embedding texts.

    Args:
        texts: List of (entity_id, embedding_text) tuples

    Returns:
        Dict with statistics:
        - total_texts
        - avg_word_count
        - min_word_count
        - max_word_count
        - avg_char_count
    """
    if not texts:
        return {
            'total_texts': 0,
            'avg_word_count': 0,
            'min_word_count': 0,
            'max_word_count': 0,
            'avg_char_count': 0
        }

    word_counts = []
    char_counts = []

    for entity_id, text in texts:
        word_counts.append(len(text.split()))
        char_counts.append(len(text))

    return {
        'total_texts': len(texts),
        'avg_word_count': sum(word_counts) / len(word_counts),
        'min_word_count': min(word_counts),
        'max_word_count': max(word_counts),
        'avg_char_count': sum(char_counts) / len(char_counts)
    }


def generate_profile_consensus_text(
    canonical_entity: dict,
    profile_key: str
) -> str:
    """
    Generate profile-specific embedding text for personalized recommendations.

    Creates rich text focused on a specific traveler profile's experience,
    including profile-specific ratings, themes, costs, and recommendations.

    Args:
        canonical_entity: Canonical entity dict from Stage 3
        profile_key: Profile key (e.g., "couple_26-35_mid-range")

    Returns:
        Profile-specific descriptive text (200-400 words typical)

    Example:
        >>> entity = load_canonical_entity("restaurant_bangkok_001")
        >>> text = generate_profile_consensus_text(entity, "couple_26-35_mid-range")
        >>> "highly rated" in text
        True
    """
    parts = []

    # 1. Entity identity
    name = canonical_entity.get('canonical_name', 'Unknown')
    entity_type = canonical_entity.get('entity_type', 'unknown')
    location = canonical_entity.get('location', 'Unknown')

    # 2. Get profile-specific metrics
    consensus = canonical_entity.get('consensus', {})
    profile_metrics = consensus.get('profile_metrics', {})

    if profile_key not in profile_metrics:
        logger.warning(f"Profile {profile_key} not found in entity consensus")
        return ""

    profile_data = profile_metrics[profile_key]

    # 3. Parse profile key
    profile_parts = profile_key.split('_')
    traveler_type = profile_parts[0] if len(profile_parts) > 0 else 'travelers'
    age_range = profile_parts[1] if len(profile_parts) > 1 else None
    budget_tier = profile_parts[2] if len(profile_parts) > 2 else None

    # Build profile description
    profile_desc = traveler_type
    if age_range and age_range != 'unknown':
        profile_desc += f" aged {age_range}"
    if budget_tier and budget_tier != 'unknown':
        profile_desc += f" on {budget_tier} budget"

    # 4. Opening with location and profile focus
    parts.append(f"{name}, a {entity_type} in {location}, as experienced by {profile_desc} travelers.")

    # 5. Profile-specific rating
    profile_rating = profile_data.get('avg_rating')
    profile_mentions = profile_data.get('mention_count', 0)

    if profile_rating is not None and profile_mentions > 0:
        if profile_rating >= 4.5:
            rating_desc = "highly rated"
            emoji = "⭐⭐⭐⭐⭐"
        elif profile_rating >= 4.0:
            rating_desc = "very well rated"
            emoji = "⭐⭐⭐⭐"
        elif profile_rating >= 3.5:
            rating_desc = "positively rated"
            emoji = "⭐⭐⭐⭐"
        elif profile_rating >= 3.0:
            rating_desc = "moderately rated"
            emoji = "⭐⭐⭐"
        else:
            rating_desc = "received mixed reviews"
            emoji = "⭐⭐"

        mention_str = f"{profile_mentions} {profile_desc} traveler{'s' if profile_mentions != 1 else ''}"
        parts.append(f"This spot is {rating_desc} ({profile_rating:.1f}/5.0 {emoji}) based on experiences from {mention_str}.")

    # 6. Profile-specific sentiment
    sentiment_dist = profile_data.get('sentiment_dist', {})
    positive = sentiment_dist.get('positive', 0)
    negative = sentiment_dist.get('negative', 0)
    neutral = sentiment_dist.get('neutral', 0)

    if positive + negative + neutral > 0:
        if positive > negative and positive > 0:
            parts.append(f"{profile_desc.capitalize()} travelers predominantly had positive experiences here.")
        elif negative > positive and negative > 0:
            parts.append(f"Some {profile_desc} travelers had concerns about this place.")
        else:
            parts.append(f"{profile_desc.capitalize()} travelers had mixed experiences.")

    # 7. Profile-specific themes
    profile_themes = profile_data.get('common_themes', [])[:8]
    if profile_themes:
        parts.append(f"Key highlights for {profile_desc} travelers: {', '.join(profile_themes)}.")

    # 8. Profile-specific cost information
    profile_cost = profile_data.get('avg_cost')
    if profile_cost:
        parts.append(f"Typical spending for {profile_desc} travelers: {profile_cost}.")

    # 9. Why it worked for this profile
    # Look at the overall consensus for comparison
    overall_rating = consensus.get('avg_rating')

    if profile_rating and overall_rating:
        if profile_rating > overall_rating + 0.5:
            parts.append(f"This {entity_type} performs exceptionally well for {profile_desc} travelers compared to other traveler types.")
        elif profile_rating < overall_rating - 0.5:
            parts.append(f"Note that {profile_desc} travelers rated this lower than average, suggesting it may not be the best fit for this traveler profile.")

    # 10. Extract profile-specific experiences
    experiences = canonical_entity.get('experiences', [])
    profile_experiences = []

    for exp in experiences:
        exp_profile = exp.get('traveler_profile', {})
        exp_type = exp_profile.get('traveler_type', 'unknown')
        exp_age = exp_profile.get('age_range', 'unknown')
        exp_budget = exp_profile.get('budget_tier', 'unknown')

        # Check if experience matches this profile
        exp_profile_key = f"{exp_type}_{exp_age}_{exp_budget}"
        if exp_profile_key == profile_key:
            exp_text = exp.get('experience', '')
            if exp_text:
                profile_experiences.append(exp_text)

    # 11. Add representative experiences
    if profile_experiences:
        sample_size = min(2, len(profile_experiences))
        sample_exps = profile_experiences[:sample_size]

        exp_texts = []
        for exp in sample_exps:
            # Truncate long experiences
            if len(exp) > 150:
                exp = exp[:147] + "..."
            exp_texts.append(exp)

        parts.append(f"What {profile_desc} travelers said: {' | '.join(exp_texts)}")

    # 12. Best for / not recommended context
    best_for = consensus.get('best_for', [])
    not_recommended_for = consensus.get('not_recommended_for', [])

    # Check if this profile is in best_for or not_recommended_for
    if any(profile_key in bf for bf in best_for):
        parts.append(f"Highly recommended for {profile_desc} travelers.")
    elif any(profile_key in nrf for nrf in not_recommended_for):
        parts.append(f"May not be ideal for {profile_desc} travelers - consider alternatives.")

    # 13. Overall location context
    coordinates = canonical_entity.get('coordinates', {})
    display_name = coordinates.get('display_name')
    if display_name:
        parts.append(f"Located at: {display_name}.")

    # 14. General entity attributes for context
    attributes = canonical_entity.get('attributes', {})
    travel_style = attributes.get('travel_style', [])

    if travel_style:
        matching_styles = [s for s in travel_style if s in profile_key or s in str(profile_themes)]
        if matching_styles:
            parts.append(f"Aligns well with {', '.join(matching_styles[:3])} travel preferences.")

    # Combine all parts
    embedding_text = " ".join(parts)

    return embedding_text


def batch_generate_profile_consensus_texts(
    entities: List[Dict[str, Any]],
    show_progress: bool = True
) -> List[Tuple[str, str, str]]:
    """
    Generate profile-specific embedding texts for all entities and their profiles.

    For each entity, generates separate embedding text for each traveler profile
    that has data (mention_count > 0).

    Args:
        entities: List of canonical entity dicts
        show_progress: Whether to show progress logging

    Returns:
        List of (entity_id, profile_key, embedding_text) tuples

    Example:
        >>> entities = load_all_canonical_entities()
        >>> texts = batch_generate_profile_consensus_texts(entities)
        >>> len(texts)
        1580  # Total profile segments across all entities
    """
    results = []
    total = len(entities)
    valid_count = 0
    invalid_count = 0
    skipped_count = 0

    logger.info(f"Generating profile-specific embedding texts for {total} entities...")

    for idx, entity in enumerate(entities, 1):
        entity_id = entity.get('entity_id', f'unknown_{idx}')

        try:
            # Get all profiles with data
            consensus = entity.get('consensus', {})
            profile_metrics = consensus.get('profile_metrics', {})

            if not profile_metrics:
                skipped_count += 1
                continue

            # Generate text for each profile
            for profile_key, profile_data in profile_metrics.items():
                mention_count = profile_data.get('mention_count', 0)

                # Skip profiles with no mentions
                if mention_count == 0:
                    skipped_count += 1
                    continue

                # Generate profile-specific text
                embedding_text = generate_profile_consensus_text(entity, profile_key)

                if not embedding_text:
                    invalid_count += 1
                    logger.warning(f"Empty text for entity {entity_id}, profile {profile_key}")
                    continue

                # Validate
                vector_id = f"{entity_id}_{profile_key}"
                if validate_embedding_text(embedding_text, vector_id):
                    results.append((entity_id, profile_key, embedding_text))
                    valid_count += 1
                else:
                    invalid_count += 1
                    logger.warning(f"Validation failed for entity {entity_id}, profile {profile_key}")

            # Progress logging
            if show_progress and idx % 100 == 0:
                logger.info(f"Progress: {idx}/{total} entities processed ({valid_count} valid, {invalid_count} invalid, {skipped_count} skipped)")

        except Exception as e:
            logger.error(f"Failed to generate profile texts for entity {entity_id}: {e}")
            invalid_count += 1

    logger.info(f"✅ Generated {valid_count} valid profile-specific texts ({invalid_count} invalid, {skipped_count} skipped)")

    return results


def generate_experience_text(
    canonical_entity: dict,
    experience: dict,
    experience_index: int
) -> str:
    """
    Generate experience-specific embedding text for individual traveler stories.

    Creates detailed text focused on one traveler's unique experience,
    preserving their voice, tips, costs, and specific details.

    Args:
        canonical_entity: Canonical entity dict from Stage 3
        experience: Single experience dict from entity.experiences array
        experience_index: Index of this experience in the array

    Returns:
        Experience-specific descriptive text (150-300 words typical)

    Example:
        >>> entity = load_canonical_entity("hotel_bangkok_001")
        >>> exp = entity['experiences'][0]
        >>> text = generate_experience_text(entity, exp, 0)
        >>> "traveler" in text.lower()
        True
    """
    parts = []

    # 1. Entity identity
    name = canonical_entity.get('canonical_name', 'Unknown')
    entity_type = canonical_entity.get('entity_type', 'unknown')
    location = canonical_entity.get('location', 'Unknown')

    # 2. Traveler profile who had this experience
    traveler_profile = experience.get('traveler_profile', {})
    traveler_type = traveler_profile.get('traveler_type', 'unknown')
    age_range = traveler_profile.get('age_range', 'unknown')
    budget_tier = traveler_profile.get('budget_tier', 'unknown')
    travel_style = traveler_profile.get('travel_style', [])

    # Build profile description
    profile_desc = traveler_type if traveler_type != 'unknown' else 'A traveler'
    if age_range != 'unknown':
        profile_desc += f" aged {age_range}"
    if budget_tier != 'unknown':
        profile_desc += f" on {budget_tier} budget"

    # Add travel style
    if travel_style:
        style_str = ', '.join(travel_style[:3])
        profile_desc += f" ({style_str}-focused)"

    # 3. Opening with traveler context
    parts.append(f"{profile_desc} visited {name}, a {entity_type} in {location}.")

    # 4. Experience text (traveler's own words)
    experience_text = experience.get('experience', '')
    if experience_text:
        # This is the traveler's story - keep it authentic
        parts.append(f"Their experience: {experience_text}")

    # 5. Sentiment and rating
    sentiment = experience.get('sentiment', 'neutral')
    confidence = experience.get('confidence_score', 0.0)

    if sentiment == 'positive':
        sentiment_desc = "had a great experience"
    elif sentiment == 'negative':
        sentiment_desc = "had some concerns"
    elif sentiment == 'mixed':
        sentiment_desc = "had mixed feelings"
    else:
        sentiment_desc = "shared their experience"

    parts.append(f"This {traveler_type} traveler {sentiment_desc} (sentiment: {sentiment}, confidence: {confidence:.0%}).")

    # 6. Cost information if mentioned
    cost_mentioned = experience.get('cost_mentioned')
    if cost_mentioned:
        parts.append(f"Cost they paid: {cost_mentioned}.")

    # 7. Timestamp context
    timestamp = experience.get('timestamp_start')
    if timestamp:
        parts.append(f"Mentioned at {timestamp:.0f} seconds in their video.")

    # 8. Source video context
    source_video_id = experience.get('source_video_id') or experience.get('video_id')
    if source_video_id:
        parts.append(f"Source: {source_video_id}.")

    # 9. Language
    language = experience.get('language', 'unknown')
    if language != 'unknown':
        parts.append(f"Shared in {language}.")

    # 10. Overall entity context for relevance
    consensus = canonical_entity.get('consensus', {})
    overall_rating = consensus.get('avg_rating')
    mention_count = consensus.get('mention_count', 0)

    if overall_rating and mention_count > 1:
        parts.append(f"Overall, this {entity_type} has been mentioned {mention_count} times with an average rating of {overall_rating:.1f}/5.0.")

    # 11. Common themes from consensus for context
    themes = consensus.get('themes', [])[:5]
    if themes:
        parts.append(f"Common themes from all travelers: {', '.join(themes)}.")

    # 12. Location details
    coordinates = canonical_entity.get('coordinates', {})
    display_name = coordinates.get('display_name')
    if display_name:
        parts.append(f"Location: {display_name}.")

    # 13. Processed timestamp
    processed_at = experience.get('processed_at')
    if processed_at:
        parts.append(f"Experience recorded: {processed_at}.")

    # Combine all parts
    embedding_text = " ".join(parts)

    return embedding_text


def batch_generate_experience_texts(
    entities: List[Dict[str, Any]],
    show_progress: bool = True
) -> List[Tuple[str, int, str]]:
    """
    Generate experience-specific embedding texts for all individual experiences.

    For each entity, generates separate embedding text for each individual
    traveler experience.

    Args:
        entities: List of canonical entity dicts
        show_progress: Whether to show progress logging

    Returns:
        List of (entity_id, experience_index, embedding_text) tuples

    Example:
        >>> entities = load_all_canonical_entities()
        >>> texts = batch_generate_experience_texts(entities)
        >>> len(texts)
        1655  # Total experiences across all entities
    """
    results = []
    total = len(entities)
    valid_count = 0
    invalid_count = 0
    skipped_count = 0

    logger.info(f"Generating experience-specific embedding texts for {total} entities...")

    for idx, entity in enumerate(entities, 1):
        entity_id = entity.get('entity_id', f'unknown_{idx}')

        try:
            # Get all experiences
            experiences = entity.get('experiences', [])

            if not experiences:
                skipped_count += 1
                continue

            # Generate text for each experience
            for exp_idx, experience in enumerate(experiences):
                # Generate experience-specific text
                embedding_text = generate_experience_text(entity, experience, exp_idx)

                if not embedding_text:
                    invalid_count += 1
                    logger.warning(f"Empty text for entity {entity_id}, experience {exp_idx}")
                    continue

                # Validate
                vector_id = f"{entity_id}_exp_{exp_idx}"
                if validate_embedding_text(embedding_text, vector_id):
                    results.append((entity_id, exp_idx, embedding_text))
                    valid_count += 1
                else:
                    invalid_count += 1
                    logger.warning(f"Validation failed for entity {entity_id}, experience {exp_idx}")

            # Progress logging
            if show_progress and idx % 100 == 0:
                logger.info(f"Progress: {idx}/{total} entities processed ({valid_count} valid, {invalid_count} invalid, {skipped_count} skipped)")

        except Exception as e:
            logger.error(f"Failed to generate experience texts for entity {entity_id}: {e}")
            invalid_count += 1

    logger.info(f"✅ Generated {valid_count} valid experience-specific texts ({invalid_count} invalid, {skipped_count} skipped)")

    return results


def calculate_total_embeddings(entities: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calculate total embeddings and costs for all three strategies.

    Args:
        entities: List of canonical entity dicts

    Returns:
        Dict with breakdown by strategy:
        - entity_level: {count, storage_mb, tokens_estimate, cost_estimate}
        - profile_aware: {count, storage_mb, tokens_estimate, cost_estimate}
        - experience_level: {count, storage_mb, tokens_estimate, cost_estimate}
        - totals: {entities, profiles, experiences}

    Example:
        >>> entities = load_all_canonical_entities()
        >>> stats = calculate_total_embeddings(entities)
        >>> stats['entity_level']['count']
        1536
    """
    # Count entities
    entity_count = len(entities)

    # Count profiles and experiences
    profile_count = 0
    experience_count = 0

    for entity in entities:
        # Count profiles with mention_count > 0
        consensus = entity.get('consensus', {})
        profile_metrics = consensus.get('profile_metrics', {})

        for profile_key, profile_data in profile_metrics.items():
            mention_count = profile_data.get('mention_count', 0)
            if mention_count > 0:
                profile_count += 1

        # Count experiences
        experiences = entity.get('experiences', [])
        experience_count += len(experiences)

    # Embedding model specs (text-embedding-3-small)
    dimensions = 1536
    bytes_per_vector = dimensions * 4  # 4 bytes per float
    kb_per_vector = bytes_per_vector / 1024
    mb_per_1k_vectors = (kb_per_vector * 1000) / 1024

    # Token estimates (rough: ~0.75 tokens per word)
    # Cost: $0.02 per 1M tokens for text-embedding-3-small

    # Entity-level
    entity_tokens_per_text = 81 * 0.75  # Average 81 words
    entity_total_tokens = entity_count * entity_tokens_per_text
    entity_cost = (entity_total_tokens / 1_000_000) * 0.02

    # Profile-aware
    profile_tokens_per_text = 70 * 0.75  # Average 70 words (shorter due to validation failures)
    profile_total_tokens = profile_count * profile_tokens_per_text
    profile_cost = (profile_total_tokens / 1_000_000) * 0.02

    # Experience-level
    exp_tokens_per_text = 150 * 0.75  # Estimate 150 words per experience
    exp_total_tokens = experience_count * exp_tokens_per_text
    exp_cost = (exp_total_tokens / 1_000_000) * 0.02

    return {
        'entity_level': {
            'count': entity_count,
            'storage_mb': (entity_count * kb_per_vector) / 1024,
            'tokens_estimate': int(entity_total_tokens),
            'cost_estimate_usd': round(entity_cost, 4)
        },
        'profile_aware': {
            'count': profile_count,
            'storage_mb': (profile_count * kb_per_vector) / 1024,
            'tokens_estimate': int(profile_total_tokens),
            'cost_estimate_usd': round(profile_cost, 4)
        },
        'experience_level': {
            'count': experience_count,
            'storage_mb': (experience_count * kb_per_vector) / 1024,
            'tokens_estimate': int(exp_total_tokens),
            'cost_estimate_usd': round(exp_cost, 4)
        },
        'totals': {
            'entities': entity_count,
            'profiles': profile_count,
            'experiences': experience_count
        }
    }


if __name__ == '__main__':
    """
    Test embedding text generation with sample entities.
    """
    from src.storage.s3 import S3Storage
    from src.storage.stage3_storage import Stage3Storage

    logger.info("=" * 80)
    logger.info("TESTING EMBEDDING TEXT GENERATION")
    logger.info("=" * 80)

    # Load sample entities
    s3_storage = S3Storage()
    storage = Stage3Storage(s3_storage=s3_storage)

    logger.info("\n📥 Loading canonical entities from S3...")
    all_entities = storage.load_all_canonical_entities()

    logger.info(f"✅ Loaded {len(all_entities)} entities")

    # Test with 5 sample entities
    sample_size = 5
    sample_entities = all_entities[:sample_size]

    logger.info(f"\n🧪 Testing with {sample_size} sample entities...")
    logger.info("=" * 80)

    for idx, entity in enumerate(sample_entities, 1):
        entity_id = entity.get('entity_id')
        canonical_name = entity.get('canonical_name')
        entity_type = entity.get('entity_type')

        logger.info(f"\n📍 Entity {idx}/{sample_size}: {canonical_name}")
        logger.info(f"   Type: {entity_type}")
        logger.info(f"   ID: {entity_id}")

        # Generate text
        embedding_text = generate_entity_embedding_text(entity)

        # Validate
        is_valid = validate_embedding_text(embedding_text, entity_id)

        # Stats
        word_count = len(embedding_text.split())
        char_count = len(embedding_text)

        logger.info(f"   Words: {word_count}")
        logger.info(f"   Characters: {char_count}")
        logger.info(f"   Valid: {'✅' if is_valid else '❌'}")
        logger.info(f"\n   Generated text:")
        logger.info(f"   {'-' * 76}")

        # Print with word wrap
        words = embedding_text.split()
        lines = []
        current_line = "   "

        for word in words:
            if len(current_line) + len(word) + 1 <= 80:
                current_line += word + " "
            else:
                lines.append(current_line.rstrip())
                current_line = "   " + word + " "

        if current_line.strip():
            lines.append(current_line.rstrip())

        for line in lines:
            logger.info(line)

        logger.info(f"   {'-' * 76}")

    # Batch generation test
    logger.info(f"\n🔄 Testing batch generation with all {len(all_entities)} entities...")

    texts = batch_generate_entity_texts(all_entities, show_progress=True)

    # Statistics
    stats = get_embedding_text_stats(texts)

    logger.info("\n📊 Embedding Text Statistics:")
    logger.info(f"   Total texts generated: {stats['total_texts']}")
    logger.info(f"   Average word count: {stats['avg_word_count']:.1f}")
    logger.info(f"   Min word count: {stats['min_word_count']}")
    logger.info(f"   Max word count: {stats['max_word_count']}")
    logger.info(f"   Average character count: {stats['avg_char_count']:.1f}")

    logger.info("\n" + "=" * 80)
    logger.info("✅ Entity-level embedding text generation test completed!")
    logger.info("=" * 80)

    # =========================================================================
    # Test Profile-Specific Embedding Generation
    # =========================================================================

    logger.info("\n\n" + "=" * 80)
    logger.info("TESTING PROFILE-SPECIFIC EMBEDDING TEXT GENERATION")
    logger.info("=" * 80)

    # Find an entity with multiple profiles (3+)
    logger.info("\n🔍 Finding entity with 3+ traveler profiles...")

    multi_profile_entity = None
    for entity in all_entities:
        consensus = entity.get('consensus', {})
        profile_metrics = consensus.get('profile_metrics', {})

        # Filter profiles with mention_count > 0
        active_profiles = {
            k: v for k, v in profile_metrics.items()
            if v.get('mention_count', 0) > 0
        }

        if len(active_profiles) >= 3:
            multi_profile_entity = entity
            break

    if multi_profile_entity:
        entity_id = multi_profile_entity.get('entity_id')
        canonical_name = multi_profile_entity.get('canonical_name')
        entity_type = multi_profile_entity.get('entity_type')
        consensus = multi_profile_entity.get('consensus', {})
        profile_metrics = consensus.get('profile_metrics', {})

        active_profiles = {
            k: v for k, v in profile_metrics.items()
            if v.get('mention_count', 0) > 0
        }

        logger.info(f"✅ Found: {canonical_name} ({entity_type})")
        logger.info(f"   Entity ID: {entity_id}")
        logger.info(f"   Active profiles: {len(active_profiles)}")
        logger.info("=" * 80)

        # Generate text for each profile
        for idx, (profile_key, profile_data) in enumerate(active_profiles.items(), 1):
            logger.info(f"\n📊 Profile {idx}/{len(active_profiles)}: {profile_key}")

            # Profile details
            profile_rating = profile_data.get('avg_rating')
            profile_mentions = profile_data.get('mention_count', 0)
            logger.info(f"   Rating: {profile_rating:.1f}/5.0")
            logger.info(f"   Mentions: {profile_mentions}")

            # Generate profile-specific text
            profile_text = generate_profile_consensus_text(multi_profile_entity, profile_key)

            # Validate
            vector_id = f"{entity_id}_{profile_key}"
            is_valid = validate_embedding_text(profile_text, vector_id)

            # Stats
            word_count = len(profile_text.split())
            char_count = len(profile_text)

            logger.info(f"   Words: {word_count}")
            logger.info(f"   Characters: {char_count}")
            logger.info(f"   Valid: {'✅' if is_valid else '❌'}")
            logger.info(f"\n   Generated text:")
            logger.info(f"   {'-' * 76}")

            # Print with word wrap
            words = profile_text.split()
            lines = []
            current_line = "   "

            for word in words:
                if len(current_line) + len(word) + 1 <= 80:
                    current_line += word + " "
                else:
                    lines.append(current_line.rstrip())
                    current_line = "   " + word + " "

            if current_line.strip():
                lines.append(current_line.rstrip())

            for line in lines:
                logger.info(line)

            logger.info(f"   {'-' * 76}")

    else:
        logger.warning("❌ No entity found with 3+ active profiles")

    # Batch profile generation test
    logger.info(f"\n\n🔄 Testing batch profile-specific generation with all {len(all_entities)} entities...")

    profile_texts = batch_generate_profile_consensus_texts(all_entities, show_progress=True)

    # Statistics
    profile_stats = get_embedding_text_stats([(f"{e}_{p}", t) for e, p, t in profile_texts])

    logger.info("\n📊 Profile-Specific Embedding Text Statistics:")
    logger.info(f"   Total profile texts generated: {profile_stats['total_texts']}")
    logger.info(f"   Average word count: {profile_stats['avg_word_count']:.1f}")
    logger.info(f"   Min word count: {profile_stats['min_word_count']}")
    logger.info(f"   Max word count: {profile_stats['max_word_count']}")
    logger.info(f"   Average character count: {profile_stats['avg_char_count']:.1f}")

    logger.info("\n" + "=" * 80)
    logger.info("✅ Profile-specific embedding text generation test completed!")
    logger.info("=" * 80)
