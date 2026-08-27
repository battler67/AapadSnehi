import { useEffect, useMemo, useState } from "react";
import {
  Zap,
  Wind,
  Waves,
  Play,
  ExternalLink,
  ShieldAlert,
  Search,
  PhoneCall,
  CheckCircle2,
  XCircle,
  Sparkles,
  Bookmark,
  Languages,
  BookOpen,
  Tv,
  Radio,
  X,
} from "lucide-react";

interface SafetyVideo {
  id: string;
  title: string;
  youtubeId: string;
  youtubeUrl: string;
  category: "lightning" | "cyclone" | "flood";
  publisher: string;
  language: "Hindi" | "English" | "Bilingual";
  duration: string;
  isHindiRecommended?: boolean;
  description: string;
  highlights: string[];
  dos: string[];
  donts: string[];
}

const SAFETY_VIDEOS: SafetyVideo[] = [
  {
    id: "lightning-precautions",
    title: "Precautions During Lightning & Thunderstorm — NDMA",
    youtubeId: "qHsORJg8Meo",
    youtubeUrl: "https://www.youtube.com/watch?v=qHsORJg8Meo",
    category: "lightning",
    publisher: "NDMA Official",
    language: "Bilingual",
    duration: "2:45",
    description: "Crucial precautions during severe thunderstorm activity to avoid lightning strikes, ground currents, and atmospheric electrical hazards.",
    highlights: [
      "Avoid standing under tall or isolated trees in open ground",
      "Stay away from open vehicles (motorcycles, tractors, convertibles)",
      "Avoid water bodies, swimming pools, and flooded grounds immediately",
      "Stay clear of exposed elevated grounds, hilltops, and metallic fences",
      "Move away from unsafe temporary shelters and tin roof sheds",
    ],
    dos: [
      "Seek shelter inside a sturdy concrete building or hard-top enclosed vehicle",
      "If caught in the open with no shelter, crouch low into a ball with hands over ears",
      "Keep feet closely together to minimize ground contact voltage",
    ],
    donts: [
      "Don't lie flat on the ground during active lightning strikes",
      "Don't take shelter under solitary tall trees or power transmission pylons",
      "Don't carry metal umbrellas or handle long metal equipment outdoors",
    ],
  },
  {
    id: "lightning-what-to-do",
    title: "What To Do During Lightning & Thunderstorm — NDMA",
    youtubeId: "t_YKlWDrKcE",
    youtubeUrl: "https://www.youtube.com/watch?v=t_YKlWDrKcE",
    category: "lightning",
    publisher: "NDMA Official",
    language: "Bilingual",
    duration: "3:10",
    description: "Indoor safety protocols, electrical appliance isolation, plumbing safety, and emergency CPR for strike victims.",
    highlights: [
      "Stay safely indoors for at least 30 minutes after the last thunder roar",
      "Close all doors and windows firmly before storm arrival",
      "Avoid contact with plumbing, taps, sinks, and running water",
      "Unplug expensive electrical appliances and avoid corded landlines",
      "Keep emergency contact numbers handy for lightning strike victims",
    ],
    dos: [
      "Use mobile phones or cordless devices instead of wired landline phones",
      "Stay inside inner rooms of concrete buildings away from metal window frames",
      "Administer immediate CPR and call 112 / 1078 if someone is struck",
    ],
    donts: [
      "Don't take a shower, bath, or wash dishes during an active thunderstorm",
      "Don't lean against concrete walls containing internal steel rebar",
      "Don't touch electrical equipment connected directly to wall outlets",
    ],
  },
  {
    id: "cyclone-before-during",
    title: "What To Do Before & During a Cyclone — NDMA",
    youtubeId: "B9qR2e3xyJo",
    youtubeUrl: "https://www.youtube.com/watch?v=B9qR2e3xyJo",
    category: "cyclone",
    publisher: "NDMA Official",
    language: "Bilingual",
    duration: "4:15",
    description: "Comprehensive cyclone preparedness, emergency survival kit assembly, food/water stockpiling, and evacuation readiness.",
    highlights: [
      "Assemble a 72-hour Emergency Kit with dry food, water, and first aid",
      "Keep battery-operated radio, flashlights, and extra batteries ready",
      "Secure vital identity documents, cash, and valuables in waterproof pouches",
      "Trim dead tree branches near home and secure loose roof sheets",
      "Stay tuned to official IMD/NDMA weather bulletins on radio and TV",
    ],
    dos: [
      "Stockpile at least 3 to 7 days of drinking water and non-perishable rations",
      "Charge mobile phones, power banks, and solar lanterns in advance",
      "Move livestock and domestic pets to safe, elevated shelters early",
    ],
    donts: [
      "Don't spread or listen to unverified rumors on social messaging apps",
      "Don't leave doors and windows unbolted or unlatched",
      "Don't delay evacuation once official cyclone warning orders are issued",
    ],
  },
  {
    id: "cyclone-indoor-safety",
    title: "Safety From Cyclones While Being Indoors — NDMA",
    youtubeId: "xNwo_a57KGc",
    youtubeUrl: "https://www.youtube.com/watch?v=xNwo_a57KGc",
    category: "cyclone",
    publisher: "NDMA Official",
    language: "Bilingual",
    duration: "3:40",
    description: "Indoor survival protocols, main utility disconnection, structural safety, and waiting for official all-clear signals.",
    highlights: [
      "Switch off main electricity breakers and LPG gas cylinder valves",
      "Secure all doors, windows, and glass panels with shutters or board tape",
      "Remain in the safest interior room away from exterior glass windows",
      "Rely exclusively on official warnings from NDMA and Meteorological Dept",
      "Remain indoors during the 'eye of the cyclone' when calm returns temporarily",
    ],
    dos: [
      "Take shelter in the strongest inner room or under heavy furniture if structure shakes",
      "Keep flashlights and battery radios within arm's reach at all times",
      "Wait for official 'all-clear' announcement before stepping outside",
    ],
    donts: [
      "Don't venture outside during sudden calm spells (winds resume fiercely from opposite direction)",
      "Don't touch fallen electrical cables or damaged power poles outside",
      "Don't attempt driving through cyclone-flooded roads or weakened bridges",
    ],
  },
  {
    id: "flood-causes-safety",
    title: "Floods: Causes & Safety Measures — Doordarshan & NDMA",
    youtubeId: "t67pFyCYSmI",
    youtubeUrl: "https://www.youtube.com/watch?v=t67pFyCYSmI",
    category: "flood",
    publisher: "Doordarshan & NDMA",
    language: "Hindi",
    duration: "5:20",
    isHindiRecommended: true,
    description: "Understanding flood dynamics, avoiding submerged electrical hazards, vehicle safety in high water, and emergency medical aid.",
    highlights: [
      "Recognize flood warning levels and river water rise indicators early",
      "Stay strictly away from fallen electric cables, transformers, and submerged poles",
      "Avoid walking, wading, or driving through swift-moving floodwaters",
      "Vehicle safety: abandon vehicle immediately if engine stalls in rising water",
      "Seek medical assistance promptly for waterborne injuries or infection symptoms",
    ],
    dos: [
      "Move to higher ground or upper floor levels immediately when flood alerts sound",
      "Drink only boiled or chemically disinfected water during flood events",
      "Keep basic medicines, mosquito nets, and disinfectant solutions in your safety kit",
    ],
    donts: [
      "Don't drive into flooded underpasses, subways, or low-lying road dips",
      "Don't allow children to swim or wade in floodwaters",
      "Don't operate electrical switches with wet hands or while standing in water",
    ],
  },
  {
    id: "flood-dos-donts-hindi",
    title: "Flood: What To Do and What Not To Do — NDMA",
    youtubeId: "8uVEwnIHHWk",
    youtubeUrl: "https://www.youtube.com/watch?v=8uVEwnIHHWk",
    category: "flood",
    publisher: "NDMA Official",
    language: "Hindi",
    duration: "4:05",
    isHindiRecommended: true,
    description: "Essential rules for Hindi-speaking citizens covering evacuation planning, emergency bag preparation, and water hygiene.",
    highlights: [
      "Comprehensive Hindi guide on immediate flood response and evacuation",
      "Community shelter protocols and relief center coordination",
      "Protection of drinking water sources from sewage contamination",
      "Safe disposal of waste and carcass management to prevent epidemics",
      "Emergency helpline numbers and rescue dispatch procedures",
    ],
    dos: [
      "Store dry food supplies in sealed waterproof containers on elevated shelves",
      "Listen to All India Radio or local news bulletins for water level advisories",
      "Help elderly, children, and expectant mothers reach relief camps first",
    ],
    donts: [
      "Don't consume food items that have come in contact with floodwater",
      "Don't ignore official evacuation warnings issued by local authorities",
      "Don't re-enter flood-damaged buildings until certified structurally safe",
    ],
  },
  {
    id: "flood-safety-measures-hindi",
    title: "Flood Safety Measures — NDMA",
    youtubeId: "0b0yrwHvCdc",
    youtubeUrl: "https://www.youtube.com/watch?v=0b0yrwHvCdc",
    category: "flood",
    publisher: "NDMA Official",
    language: "Hindi",
    duration: "3:50",
    isHindiRecommended: true,
    description: "Detailed safety guidelines in Hindi focusing on post-flood health, water purification, and sanitation precautions.",
    highlights: [
      "Purification techniques for well and tap water after flood inundation",
      "Use of bleaching powder and ORS packets for disease prevention",
      "Inspection of house foundation and electrical wiring after water recedes",
      "Vector control and mosquito breeding prevention around living areas",
      "Reporting missing persons and contacting NDRF / State Disaster Response Teams",
    ],
    dos: [
      "Use chlorine tablets or boil water for at least 10 minutes before consumption",
      "Disinfect flooded premises with bleaching powder once water recedes",
      "Report damaged roads, bridges, and electric poles to local control room",
    ],
    donts: [
      "Don't use electrical appliances that were submerged until tested by an electrician",
      "Don't consume open street food or unboiled water post-flooding",
      "Don't walk through stagnant floodwater without protective rubber boots",
    ],
  },
];

const EMERGENCY_CONTACTS = [
  { name: "National Emergency", number: "112", dial: "112", subtitle: "All-in-one emergency line", icon: PhoneCall, tone: "critical" },
  { name: "NDMA Control Room", number: "1078", dial: "1078", subtitle: "Disaster helpline", icon: ShieldAlert, tone: "warning" },
  { name: "State Relief Center", number: "1070", dial: "1070", subtitle: "State control room", icon: Radio, tone: "signal" },
  { name: "Fire & Rescue", number: "101", dial: "101", subtitle: "Fire and rescue", icon: PhoneCall, tone: "fire" },
  { name: "Medical Ambulance", number: "108 / 102", dial: "108", subtitle: "Medical dispatch", icon: PhoneCall, tone: "medical" },
];

// Helper Component: Robust YouTube Thumbnail Component with automatic fallback
const ThumbnailImage: React.FC<{ youtubeId: string; title: string }> = ({ youtubeId, title }) => {
  const [src, setSrc] = useState(`https://i.ytimg.com/vi/${youtubeId}/maxresdefault.jpg`);

  return (
    <img
      src={src}
      alt={title}
      onError={() => {
        if (src.includes("maxresdefault")) {
          setSrc(`https://i.ytimg.com/vi/${youtubeId}/hqdefault.jpg`);
        } else if (src.includes("hqdefault")) {
          setSrc(`https://i.ytimg.com/vi/${youtubeId}/mqdefault.jpg`);
        } else if (src.includes("mqdefault")) {
          setSrc(`https://i.ytimg.com/vi/${youtubeId}/0.jpg`);
        }
      }}
      className="safety-thumbnail-image"
      loading="lazy"
    />
  );
};

export function SafetyPage() {
  const [selectedCategory, setSelectedCategory] = useState<string>("all");
  const [hindiOnly, setHindiOnly] = useState<boolean>(false);
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [activeVideoId, setActiveVideoId] = useState<string | null>("qHsORJg8Meo");
  const [modalVideoId, setModalVideoId] = useState<string | null>(null);
  const [activeChecklistCategory, setActiveChecklistCategory] = useState<"lightning" | "cyclone" | "flood">("lightning");

  useEffect(() => {
    if (!modalVideoId) return undefined;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setModalVideoId(null);
    };
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [modalVideoId]);

  const filteredVideos = useMemo(() => {
    return SAFETY_VIDEOS.filter((video) => {
      if (selectedCategory !== "all" && video.category !== selectedCategory) {
        return false;
      }
      if (hindiOnly && video.language !== "Hindi" && !video.isHindiRecommended) {
        return false;
      }
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchTitle = video.title.toLowerCase().includes(q);
        const matchDesc = video.description.toLowerCase().includes(q);
        const matchHighlights = video.highlights.some((h) => h.toLowerCase().includes(q));
        if (!matchTitle && !matchDesc && !matchHighlights) {
          return false;
        }
      }
      return true;
    });
  }, [selectedCategory, hindiOnly, searchQuery]);

  const activeVideo = useMemo(() => {
    return SAFETY_VIDEOS.find((v) => v.youtubeId === activeVideoId) || SAFETY_VIDEOS[0];
  }, [activeVideoId]);

  const modalVideo = useMemo(() => {
    return SAFETY_VIDEOS.find((v) => v.youtubeId === modalVideoId) || null;
  }, [modalVideoId]);

  const checklistItems = useMemo(() => {
    return SAFETY_VIDEOS.filter((v) => v.category === activeChecklistCategory);
  }, [activeChecklistCategory]);

  const getCategoryLabel = (category: string) => {
    switch (category) {
      case "lightning":
        return "Lightning & Thunderstorm";
      case "cyclone":
        return "Cyclone Safety";
      case "flood":
        return "Flood Measures";
      default:
        return "Disaster Guide";
    }
  };

  return (
    <div className="safety-page">
      {/* Centered Hero Banner */}
      <header className="safety-hero">
        {/* Glow Spheres */}
        <div className="safety-hero-glow" aria-hidden="true" />

        <div className="safety-hero-copy">
          {/* Centered Eyebrow Pill */}
          <div className="safety-kicker">
            <Sparkles size={15} />
            <span>Official Response & Public Safety Intelligence</span>
          </div>

          {/* Centered Main Title */}
          <h1>
            Disaster Safety &{" "}
            <span>
              Preparedness Hub
            </span>
          </h1>

          {/* Centered Subtitle */}
          <p className="safety-hero-lead">
            Verified educational video guides, emergency action protocols, and precaution checklists published by the{" "}
            <strong>National Disaster Management Authority (NDMA)</strong> and{" "}
            <strong>Doordarshan</strong>.
          </p>

          {/* Centered Stats & Topic Pills */}
          <div className="safety-topic-row">
            <div data-category="lightning">
              <Zap size={15} /> Lightning & Thunderstorm
            </div>
            <div data-category="cyclone">
              <Wind size={15} /> Cyclone Safety
            </div>
            <div data-category="flood">
              <Waves size={15} /> Flood Protection
            </div>
            <div data-category="language">
              <Languages size={15} /> Hindi & English Videos
            </div>
          </div>
        </div>

        {/* Centered Emergency Helplines Strip */}
        <div className="safety-emergency-strip">
          <div className="safety-emergency-label">
            <PhoneCall size={15} /> 24/7 national emergency helplines
          </div>

          <div className="safety-contact-grid">
            {EMERGENCY_CONTACTS.map((item) => (
              <a
                key={item.name}
                href={`tel:${item.dial}`}
                className="safety-contact-card"
                data-tone={item.tone}
              >
                <div className="safety-contact-name">
                  <item.icon size={14} />
                  <span>{item.name}</span>
                </div>
                <strong>{item.number}</strong>
                <small>{item.subtitle}</small>
              </a>
            ))}
          </div>
        </div>
      </header>

      {/* Main Content Area - Centered Alignment */}
      <main className="content safety-main">
        {/* Featured Cinema Theater Video Player - Centered */}
        {activeVideo && (
          <section className="glass-panel safety-featured" data-category={activeVideo.category}>
            <div className="safety-featured-head">
              <div className="safety-meta-row">
                <span className="safety-category-badge" data-category={activeVideo.category}>
                  {getCategoryLabel(activeVideo.category)}
                </span>
                <span className="safety-language-badge">
                  {activeVideo.language} Audio
                </span>
                {activeVideo.isHindiRecommended && (
                  <span className="safety-language-badge recommended">
                    Recommended Hindi Guide
                  </span>
                )}
              </div>

              <h2>{activeVideo.title}</h2>
              <p>
                <Tv size={14} /> Source: <strong>{activeVideo.publisher}</strong> <span>•</span> Duration: {activeVideo.duration}
              </p>
            </div>

            {/* Theater Video Player Frame */}
            <div className="safety-featured-player">
              <iframe
                src={`https://www.youtube-nocookie.com/embed/${activeVideo.youtubeId}?autoplay=0&rel=0`}
                title={activeVideo.title}
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowFullScreen
                className="safety-video-frame"
              />
            </div>

            {/* Centered Highlights & Takeaways */}
            <div className="safety-featured-details">
              <div className="safety-info-panel overview">
                <div className="safety-panel-label">
                  <Bookmark size={15} /> Video overview
                </div>
                <p>
                  {activeVideo.description}
                </p>
              </div>

              <div className="safety-info-panel precautions">
                <div className="safety-panel-label">
                  <CheckCircle2 size={15} /> Essential precautions covered
                </div>
                <ul>
                  {activeVideo.highlights.slice(0, 4).map((point, idx) => (
                    <li key={idx}>
                      <span aria-hidden="true" />
                      <span>{point}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </section>
        )}

        {/* Video Library Section */}
        <section className="safety-library">
          <div className="safety-section-heading">
            <span className="safety-section-icon"><BookOpen size={20} /></span>
            <div>
            <h2>Official disaster video guides</h2>
            <p>
              Select a trusted guide, scan its key precautions, or open the full-screen player.
            </p>
            </div>
            <span className="safety-result-count">{filteredVideos.length} of {SAFETY_VIDEOS.length} guides</span>
          </div>

          <div className="safety-library-controls">
            <div className="safety-filter-tabs" aria-label="Filter guides by disaster" role="group">
              <button
                type="button"
                onClick={() => setSelectedCategory("all")}
                className="safety-filter-chip"
                data-active={selectedCategory === "all"}
                aria-pressed={selectedCategory === "all"}
              >
                All guides <span>{SAFETY_VIDEOS.length}</span>
              </button>

              <button
                type="button"
                onClick={() => setSelectedCategory("lightning")}
                className="safety-filter-chip"
                data-category="lightning"
                data-active={selectedCategory === "lightning"}
                aria-pressed={selectedCategory === "lightning"}
              >
                <Zap size={15} /> Lightning
              </button>

              <button
                type="button"
                onClick={() => setSelectedCategory("cyclone")}
                className="safety-filter-chip"
                data-category="cyclone"
                data-active={selectedCategory === "cyclone"}
                aria-pressed={selectedCategory === "cyclone"}
              >
                <Wind size={15} /> Cyclone
              </button>

              <button
                type="button"
                onClick={() => setSelectedCategory("flood")}
                className="safety-filter-chip"
                data-category="flood"
                data-active={selectedCategory === "flood"}
                aria-pressed={selectedCategory === "flood"}
              >
                <Waves size={15} /> Flood
              </button>
            </div>

            <div className="safety-secondary-filters">
              <button
                type="button"
                onClick={() => setHindiOnly(!hindiOnly)}
                className="safety-language-filter"
                data-active={hindiOnly}
                aria-pressed={hindiOnly}
              >
                <Languages size={15} />
                <span>{hindiOnly ? "Showing Hindi guides" : "Hindi audio"}</span>
              </button>

              <label className="safety-search">
                <span className="safety-visually-hidden">Search safety guides</span>
                <Search size={16} />
                <input
                  type="search"
                  placeholder="Search topics or precautions"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
                {searchQuery && <button type="button" onClick={() => setSearchQuery("")} aria-label="Clear search"><X size={14} /></button>}
              </label>
            </div>
          </div>

          <div className="safety-video-grid">
            {filteredVideos.map((video) => {
              const isPlaying = activeVideoId === video.youtubeId;
              const categoryLabel = getCategoryLabel(video.category);

              return (
                <div
                  key={video.id}
                  className="safety-video-card"
                  data-category={video.category}
                  data-active={isPlaying}
                >
                  {/* High Quality Video Preview Thumbnail */}
                  <div className="safety-card-media">
                    <ThumbnailImage youtubeId={video.youtubeId} title={video.title} />
                    <div className="safety-card-scrim" />

                    {/* Category & Language Badges */}
                    <div className="safety-card-badges">
                      <span className="safety-category-badge" data-category={video.category}>
                        {categoryLabel}
                      </span>
                      {video.language === "Hindi" && (
                        <span className="safety-language-badge recommended">
                          Hindi Audio
                        </span>
                      )}
                    </div>

                    {/* Duration Badge */}
                    <div className="safety-duration">
                      {video.duration}
                    </div>

                    {/* Interactive Play Button Overlay */}
                    <button
                      type="button"
                      onClick={() => {
                        setActiveVideoId(video.youtubeId);
                        setModalVideoId(video.youtubeId);
                      }}
                      className="safety-card-play-overlay"
                      aria-label={`Play ${video.title}`}
                    >
                      <span><Play size={22} fill="currentColor" /></span>
                    </button>
                  </div>

                  {/* Card Content Body */}
                  <div className="safety-card-body">
                    <div>
                      <h3>
                        {video.title}
                      </h3>
                      <p>{video.description}</p>
                    </div>

                    {/* Key points list */}
                    <div className="safety-card-highlights">
                      <strong>Key highlights</strong>
                      {video.highlights.slice(0, 2).map((h, i) => (
                        <div key={i}>
                          <span aria-hidden="true" />
                          <span>{h}</span>
                        </div>
                      ))}
                    </div>

                    {/* Card Actions */}
                    <div className="safety-card-actions">
                      <button
                        type="button"
                        onClick={() => {
                          setActiveVideoId(video.youtubeId);
                          setModalVideoId(video.youtubeId);
                        }}
                        className="safety-watch-button"
                      >
                        <Play size={14} fill="currentColor" /> Watch video
                      </button>

                      <a
                        href={video.youtubeUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="safety-external-link"
                      >
                        YouTube <ExternalLink size={13} />
                      </a>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {filteredVideos.length === 0 && (
            <div className="safety-empty-state">
              <ShieldAlert size={34} />
              <h3>No guides match your search</h3>
              <p>
                Try resetting your filters or clearing search terms to explore all educational videos.
              </p>
              <button
                type="button"
                onClick={() => {
                  setSelectedCategory("all");
                  setHindiOnly(false);
                  setSearchQuery("");
                }}
                className="safety-watch-button"
              >
                Reset Filters
              </button>
            </div>
          )}
        </section>

        {/* Centered Actionable Emergency Do's & Don'ts Checklist */}
        <section className="safety-checklist-section">
          <div className="safety-section-heading checklist-heading">
            <span className="safety-section-icon"><ShieldAlert size={20} /></span>
            <div>
            <h2>Emergency do's and don'ts</h2>
            <p>Quick actions to remember before conditions become critical.</p>
            </div>
          </div>

          {/* Centered Category Switcher */}
          <div className="safety-checklist-tabs" role="group" aria-label="Select checklist disaster">
            <button
              type="button"
              onClick={() => setActiveChecklistCategory("lightning")}
              className="safety-checklist-tab"
              data-category="lightning"
              data-active={activeChecklistCategory === "lightning"}
              aria-pressed={activeChecklistCategory === "lightning"}
            >
              <Zap size={15} /> Lightning
            </button>
            <button
              type="button"
              onClick={() => setActiveChecklistCategory("cyclone")}
              className="safety-checklist-tab"
              data-category="cyclone"
              data-active={activeChecklistCategory === "cyclone"}
              aria-pressed={activeChecklistCategory === "cyclone"}
            >
              <Wind size={15} /> Cyclone
            </button>
            <button
              type="button"
              onClick={() => setActiveChecklistCategory("flood")}
              className="safety-checklist-tab"
              data-category="flood"
              data-active={activeChecklistCategory === "flood"}
              aria-pressed={activeChecklistCategory === "flood"}
            >
              <Waves size={15} /> Flood
            </button>
          </div>

          {/* Centered Cards Split */}
          <div className="safety-checklist-grid">
            {/* DO's */}
            <div className="safety-checklist-card do">
              <div className="safety-checklist-card-head">
                <CheckCircle2 size={22} />
                <span>Recommended actions</span>
                <small>{activeChecklistCategory}</small>
              </div>
              <ul>
                {checklistItems.flatMap((item) => item.dos).map((doItem, idx) => (
                  <li key={idx}>
                    <span aria-hidden="true">✓</span>
                    <span>{doItem}</span>
                  </li>
                ))}
              </ul>
            </div>

            {/* DONT's */}
            <div className="safety-checklist-card dont">
              <div className="safety-checklist-card-head">
                <XCircle size={22} />
                <span>Critical actions to avoid</span>
                <small>{activeChecklistCategory}</small>
              </div>
              <ul>
                {checklistItems.flatMap((item) => item.donts).map((dontItem, idx) => (
                  <li key={idx}>
                    <span aria-hidden="true">✕</span>
                    <span>{dontItem}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </section>
      </main>

      {/* Pop-up Video Modal Player */}
      {modalVideo && (
        <div
          className="safety-modal-backdrop"
          onClick={(e) => {
            if (e.target === e.currentTarget) setModalVideoId(null);
          }}
          role="presentation"
        >
          <div className="safety-modal" role="dialog" aria-modal="true" aria-labelledby="safety-modal-title">
            <div className="safety-modal-head">
              <div>
                <span>Official safety guide</span>
                <h3 id="safety-modal-title">{modalVideo.title}</h3>
                <p>{modalVideo.publisher} <span>•</span> {modalVideo.language} audio</p>
              </div>
              <button
                type="button"
                onClick={() => setModalVideoId(null)}
                className="safety-modal-close"
                aria-label="Close video"
              >
                <X size={18} />
              </button>
            </div>

            <div className="safety-modal-player">
              <iframe
                src={`https://www.youtube-nocookie.com/embed/${modalVideo.youtubeId}?autoplay=1&rel=0`}
                title={modalVideo.title}
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowFullScreen
                className="safety-video-frame"
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
