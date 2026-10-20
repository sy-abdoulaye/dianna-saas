# Modèle de données

Conventions : tous les modèles marqués **(T)** héritent de `TenantModel` (champ `company`, gestionnaire filtrant). Tous ont `created_at` et `updated_at` (mixin `Timestamped`). Tout modèle adressé par une URL (fiche salarié, demandes, équipements, annonces, questionnaires, entretiens, comptes rendus) a un champ `public_id` (UUID, unique, indexé) utilisé dans les URL à la place de l'identifiant numérique, pour ne pas révéler de volumes. Les énumérations sont des `TextChoices` dont les libellés français viennent du prototype.

## Socle (`core`, `accounts`)

**Company** (pas de company)

| Champ | Type | Notes |
|---|---|---|
| name | char 120 | « Exemple SAS » |
| slug | slug unique | sous-domaine ; réservés : www, admin, api, static, media, mail, support |
| status | choix : active, suspended | |
| logo | image, optionnel | PNG ou JPG, 1 Mo ; stockage privé, URL signée (L2-01) |
| telework_max_per_week | small int, défaut 2 | M-01, 0 à 5 |
| telework_auto_approve | bool, défaut False | M-02 |
| summer_leave_hr_step | bool, défaut True | M-03 : validation finale RH des congés d'été |
| timezone | char, défaut Europe/Paris | |

**CompanyModule** (T) : `module` (choix : planning, telework, summer_leave, on_call, transport, equipment, announcements, surveys, careers, interventions), `enabled` (bool). Unique (company, module). Le socle, l'annuaire (L1-05) et l'administration ne sont pas désactivables.

**Site** (T) : `name`, `address` optionnel. Unique (company, `Lower(name)`).
**Service** (T) : `name`. Unique (company, `Lower(name)`).
**Closure** (T) : `date`, `label`, `site` optionnel (fermetures d'entreprise ; les jours fériés viennent du paquet `holidays`).

**User** (pas de company ; `AbstractBaseUser` + `PermissionsMixin`, créé au lot 0, L0-01) : `email` unique sans tenir compte de la casse (stocké en minuscules), `is_active`, `is_staff` (équipe Dianna : super-administrateur éditeur, accès à l'administration Django ; propriété `is_platform_staff`), `is_superuser`, groupes et permissions Django, `theme` (system, light, dark), `last_login`. Connexion par e-mail.

**Invitation** (T) : `employee`, `token_hash` (SHA-256 du jeton, le jeton n'est jamais stocké), `expires_at` (7 jours), `accepted_at`, `revoked_at` (remplacée par une nouvelle invitation), `sent_at`, `send_failed_at`, `renewal_requested_at` (lien expiré : administrateurs prévenus une seule fois), `sent_by`. Le jeton est créé par la tâche d'envoi : jusqu'à ce que l'e-mail soit accepté par le serveur d'envoi, `token_hash` est une **empreinte provisoire** qui ne correspond à aucun lien, et l'invitation précédente reste valable. À l'envoi réussi et confirmé : empreinte du vrai jeton, `sent_at`, et les invitations **plus anciennes** de la fiche sont remplacées (`revoked_at`), sous verrou ; une invitation remplacée entre-temps par une plus récente ne remplace rien, et une invitation plus récente encore en attente d'envoi n'est jamais remplacée. En cas d'échec de l'envoi ou de sa confirmation : `send_failed_at`, état **« Envoi échoué »** dans « Utilisateurs et profils », avec « Renvoyer l'invitation » (A3-04).

**AuditLog** (T) : `actor` (Employee, nul pour la plateforme), `action` (char), `target_type`, `target_id`, `summary` (texte sans donnée sensible), `ip`, `created_at`. Index (company, created_at).

**Notification** (T) : `recipient` (Employee), `text`, `url`, `kind`, `read_at`, `created_at`, `email_sent_at`, `email_subject` (objet de l'e-mail, vide si la notification ne part pas par e-mail ; le corps est construit à l'envoi), `source_type` et `source_id` (demande concernée : les notifications non encore envoyées par e-mail sont retirées quand une transition les rend fausses, A3-05). Index (recipient, read_at).

## Annuaire (`people`)

**Employee** (T)

| Champ | Type | Notes |
|---|---|---|
| user | OneToOne User, nul | nul tant que l'invitation n'est pas acceptée |
| first_name, last_name | char | |
| email | email | contact professionnel, unique par entreprise, insensible à la casse : `UniqueConstraint(Lower("email"), "company")`. Distinct de l'identifiant `User.email` (T-09) |
| phone, office | char, optionnels | |
| photo | image, optionnel | ≤ 2 Mo, JPG ou PNG ; stockage privé, réencodée sans EXIF (L2-02) |
| job_title | char | |
| service | FK Service, `RESTRICT`, nul permis (premier administrateur) | obligatoire dans le formulaire (lot 2) |
| site | FK Site, `RESTRICT`, nul permis | obligatoire dans le formulaire (lot 2) |
| manager | FK self, nul | définit l'équipe ; toute fiche active (L1-02) |
| role | choix : employee, manager, hr, admin | profil d'accès |
| status | choix : active, upcoming, left | « Actif », « Arrivée prochaine », « Parti » |
| arrival_date, departure_date | date | departure nul si en poste |
| contract_type | choix : CDI, CDD, alternance, stage | RH |
| work_time | choix : full_35, part_28, days_package | RH |
| registration_number | char | matricule, RH, unique par entreprise |
| telework_days_override | small int, nul | dérogation au quota |

Index : (company, last_name), (company, service), (company, manager). Le statut `upcoming` passe à `active` à la date d'arrivée (tâche quotidienne).

**EmployeeChange** (T) : historique de la fiche : `employee`, `actor`, `kind` (created, updated, contact, archived, reactivated, role, imported), `fields` (JSON des noms de champs modifiés, jamais les valeurs), `created_at`.

## Agenda (`agenda`)

**CalendarEvent** (T) : `employee`, `kind` (telework, leave, on_call), `start`, `end` (dates incluses), `status` (pending, approved), `source_type`, `source_id`. Index (company, start, end), (employee, start). Unique (company, source_type, source_id) ; fin ≥ début. Les demandes refusées ou annulées suppriment leur événement.

## Demandes (`approvals`)

Base abstraite **ApprovalRequest** (T) : `public_id`, `requester` (Employee), `status` (pending, manager_approved, approved, refused, cancelled), `submitted_at`, `decided_by` (Employee, nul), `decided_at`, `decision_comment`. Le statut `manager_approved` n'est utilisé que par les congés d'été quand l'étape RH est active.

**RequestEvent** (T) : historique générique : `request_type`, `request_id`, `actor` (nul pour une validation automatique), `action` (submitted, auto_approved, manager_approved, approved, refused, cancelled, reverted), `comment`, `created_at`.

| Modèle | Champs propres | Contraintes |
|---|---|---|
| **TeleworkRequest** | `date`, `comment` | jour ouvré, pas dans le passé, une seule demande active par jour (contrainte unique partielle en base), quota hebdomadaire (pending + approved) |
| **SummerCampaign** | `label` (« Été 2027 »), `period_start`, `period_end`, `deadline`, `status` (draft, open, closed), `conflict_threshold` (%, défaut 30) | une seule campagne ouverte (contrainte unique partielle) ; fin ≥ début |
| **LeaveRequest** | `campaign` (nul pour une autre absence), `start`, `end`, `leave_type` (summer, other), `comment`, `manager_decided_by`, `manager_decided_at` (première décision ; la décision finale RH utilise `decided_by` et `decided_at`) | fin ≥ début, ≤ 31 jours, pas de chevauchement avec ses demandes actives |
| **OnCallDeclaration** | `kind` (on_call, intervention), `start`, `end` (dates incluses), `hours` (décimal, obligatoire si intervention, ≤ 24), `description` | fin ≥ début ; seul `on_call` crée un `CalendarEvent` |
| **TransportProof** | `month` (date au 1er du mois, début de validité), `ticket_type` (monthly, yearly, single), `amount` (décimal), `file`, `valid_until` (calculé : fin du mois pour mensuel et titre unique, mois + 12 − 1 jour pour annuel) | pas de chevauchement de validité entre deux justificatifs actifs du même salarié et du même type ; montant > 0 et ≤ 1 000 |

Remboursement estimé calculé à l'affichage (50 %, M-06), jamais stocké comme montant payé.

## Matériel (`equipment`)

**EquipmentItem** (T) : `kind` (laptop, screen, headset, phone, other), `model`, `serial_number` (unique par entreprise), `status` (in_stock, assigned, repair, retired), `holder` (Employee, nul), `assigned_at`.
**EquipmentAssignment** (T) : historique : `item`, `employee`, `assigned_at`, `returned_at`, `assigned_by`, `request` (EquipmentRequest, nul).
**EquipmentIssue** (T) : `item`, `reported_by`, `description`, `status` (open, closed), `closed_by`, `closed_at`, `resolution`.
**EquipmentRequest** (T, hérite d'ApprovalRequest) : `kind`, `reason`.

## Communication interne (`announcements`)

**Announcement** (T) : `title`, `category` (company, hr, site_life, safety), `body` (texte), `pinned`, `author`, `published_at`, `audience` (all ; services et sites ciblés : lot 8).
**AnnouncementRead** (T) : `announcement`, `employee`, `read_at`. Unique (announcement, employee).

## Questionnaires (`surveys`)

**Survey** (T) : `title`, `audience` (all, managers, new_hires), `due_date`, `status` (draft, open, closed), `created_by`, `anonymity_threshold` (défaut 3).
**Question** (T) : `survey`, `order`, `kind` (scale_1_5, text), `label`, `required`.
**SurveyReceipt** (T) : `survey`, `employee`, `answered_at`. Unique (survey, employee). Sert uniquement à savoir qui a répondu.
**SurveyResponse** (T) : clé primaire **UUID aléatoire**, `survey`, `submitted_on` (date seule). **Aucun lien vers le salarié.**
**Answer** (T) : clé primaire UUID aléatoire, `response`, `question`, `score` (1 à 5, nul), `text`, `comment` (justification facultative de la note).

`SurveyResponse` et `Answer` **n'héritent pas** du mixin `Timestamped` (pas d'horodatage précis, pas de clé séquentielle) : sinon on retrouverait le répondant en rapprochant l'ordre des reçus et des réponses. Le reçu et la réponse sont créés dans la même transaction, sans clé commune. Un test vérifie qu'aucun champ de `SurveyResponse` ou `Answer` ne permet de les trier dans l'ordre des reçus.

## Carrière (`careers`)

**ReviewCampaign** (T) : `label` (« Campagne 2026 »), `start`, `end`.
**Competency** (T) : `name`, `description`, `order` (paramétrable ; 4 par défaut : relation client, autonomie, travail en équipe, maîtrise des outils).
**Review** (T)

| Champ | Notes |
|---|---|
| campaign (nul), employee, manager | manager copié au lancement |
| kind | individual, professional |
| step | self, manager, meeting, signature, closed. Ordre : individuel = self → manager → meeting → signature ; professionnel = self → meeting → manager → signature |
| meeting_date, meeting_place | |
| self_summary, self_project | partie salarié |
| manager_summary, strengths, improvements, report | partie manager |
| employee_comment | commentaire du salarié avant signature |
| six_year_training, six_year_certification, six_year_progression | bool, nul (entretien professionnel : bilan à 6 ans) |
| six_year_due | date |
| employee_signed_at, manager_signed_at, signed_by_hr | signatures |

**ReviewRating** (T) : `review`, `competency`, `score` (1 à 4).
**ReviewObjective** (T) : `review`, `title`, `due_date`, `result` (nul).
**ReviewTraining** (T) : `review`, `label`.
**FollowUpNote** (T) : `employee`, `author`, `date`, `kind` (follow_up, wish, training, review), `text`, `is_private` (visible par l'auteur seul).

## Suivi d'intervention (`interventions`)

**Mission** (T) : `name` (ex. « Migration de la messagerie · Groupe Horizon »), `client` optionnel, `active`.
**InterventionReport** (T)

| Champ | Notes |
|---|---|
| employee, mission | |
| period | date au 1er du mois |
| status | draft, submitted, approved, changes_requested |
| visibility | planned_end, extension_likely, extension_confirmed, uncertain |
| planned_end | date |
| extension_wanted | bool |
| extension_until | date, > planned_end |
| follow_up | texte : points de suivi, risques, besoins |
| reviewer_note | remarque du manager |

Unique (company, employee, mission, period).

**ReportItem** (T) : `report`, `section` (done, next), `order`, `description`, `difficulties`, `solutions` (section done seulement), `completion` (0 à 100), `due_date`, `comments`.
**ReportEvent** (T) : `report`, `actor`, `action`, `comment`, `created_at`.
